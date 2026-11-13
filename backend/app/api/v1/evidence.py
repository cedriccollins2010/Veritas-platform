"""Routes /api/v1/evidence. Logique dans app.evidence (service, upload)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import Client, CurrentOrganization, CurrentUser
from app.core.config import get_settings
from app.crypto.custody_chain import verify_chain
from app.crypto.hash_service import normalize_digest
from app.custody import service as custody_service
from app.custody.schemas import (
    ChainVerificationOut,
    CustodyEventOut,
    EvidenceEventsOut,
)
from app.database.session import get_db
from app.evidence import service
from app.evidence.schemas import EvidenceOut, HashOnlyRequest
from app.evidence.upload import (
    InvalidUploadError,
    UploadTooLargeError,
    clean_filename,
    clean_media_type,
    receive_upload,
)
from app.storage import Storage, get_storage

router = APIRouter(prefix="/evidence", tags=["evidence"])

Db = Annotated[Session, Depends(get_db)]
StorageDep = Annotated[Storage, Depends(get_storage)]

NOT_FOUND = "Preuve introuvable."


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceOut,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "title": {"type": "string", "maxLength": 255},
                        },
                    }
                }
            },
        }
    },
)
async def create_evidence(
    request: Request,
    user: CurrentUser,
    membership: CurrentOrganization,
    db: Db,
    storage: StorageDep,
    client: Client,
) -> EvidenceOut:
    """Dépose un fichier : il est haché (SHA-256) pendant la réception, stocké, et la
    preuve est créée à l'état HASHED avec son premier événement de possession.

    L'authentification et le jeton CSRF sont vérifiés avant de lire le moindre octet."""
    settings = get_settings()
    user_id, organization_id = user.id, membership.organization.id
    # Les vérifications d'accès ont ouvert une transaction de lecture. On la termine
    # avant de recevoir le fichier : sinon une connexion à la base resterait occupée
    # pendant tout l'envoi (plusieurs minutes pour 500 Mo sur une liaison lente), et
    # quelques dépôts simultanés suffiraient à épuiser le pool de connexions.
    db.commit()
    try:
        upload = await receive_upload(
            request,
            max_file_bytes=settings.max_upload_size_mb * 1024 * 1024,
            temp_dir=settings.upload_temp_dir,
        )
    except UploadTooLargeError:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Fichier trop volumineux (maximum {settings.max_upload_size_mb} Mo).",
        ) from None
    except InvalidUploadError as error:
        raise HTTPException(error.status_code, detail=str(error)) from None

    try:
        view = await run_in_threadpool(
            service.create_from_upload,
            db,
            storage,
            upload,
            user_id=user_id,
            organization_id=organization_id,
            client=client,
        )
    except service.EvidenceCreationError as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Le dépôt a échoué ; la preuve {error.evidence_id} est marquée FAILED.",
        ) from None
    finally:
        upload.discard()
    return EvidenceOut.from_view(view)


@router.post(
    "/hash-only",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceOut,
)
def create_hash_only_evidence(
    body: HashOnlyRequest,
    user: CurrentUser,
    membership: CurrentOrganization,
    db: Db,
    client: Client,
) -> EvidenceOut:
    """Mode « empreinte seule » : enregistre l'empreinte SHA-256 d'un fichier qui reste
    sous la garde de l'analyste (image disque, capture réseau). Le fichier n'est pas
    envoyé. La réponse indique verified_by_server = false : VERITAS atteste avoir reçu
    cette empreinte à cette date, pas l'avoir calculée."""
    try:
        digest = normalize_digest(body.sha256)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    view = service.create_hash_only(
        db,
        service.DeclaredHash(
            original_filename=clean_filename(body.original_filename.encode("utf-8")),
            media_type=clean_media_type(body.media_type),
            size=body.size,
            sha256=digest,
            title=body.title,
            hash_tool=body.hash_tool or "non précisé",
        ),
        user_id=user.id,
        organization_id=membership.organization.id,
        client=client,
    )
    return EvidenceOut.from_view(view)


@router.get("", response_model=list[EvidenceOut])
def list_evidence(
    membership: CurrentOrganization,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EvidenceOut]:
    views = service.list_for_organization(
        db, membership.organization.id, limit=limit, offset=offset
    )
    return [EvidenceOut.from_view(view) for view in views]


@router.get("/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: uuid.UUID, membership: CurrentOrganization, db: Db) -> EvidenceOut:
    view = service.get_for_organization(db, membership.organization.id, evidence_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return EvidenceOut.from_view(view)


@router.get("/{evidence_id}/events", response_model=EvidenceEventsOut)
def get_evidence_events(
    evidence_id: uuid.UUID, membership: CurrentOrganization, db: Db
) -> EvidenceEventsOut:
    """Historique (chaîne de possession) d'une preuve, avec la vérification de la chaîne."""
    if service.get_for_organization(db, membership.organization.id, evidence_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    events = custody_service.list_events(db, evidence_id)
    verification = verify_chain([custody_service.to_chain_event(e) for e in events])
    return EvidenceEventsOut(
        evidence_id=evidence_id,
        events=[CustodyEventOut.from_model(event) for event in events],
        chain=ChainVerificationOut.from_result(verification),
    )
