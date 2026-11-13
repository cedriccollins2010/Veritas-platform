"""Routes /api/v1/evidence. Logique dans app.evidence (service, upload)."""

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from veritas_verifier.custody_chain import verify_chain
from veritas_verifier.hash_service import normalize_digest

from app.auth.dependencies import Client, CurrentOrganization, CurrentUser
from app.core.config import get_settings
from app.custody import service as custody_service
from app.custody.schemas import (
    ChainVerificationOut,
    CustodyEventOut,
    EvidenceEventsOut,
)
from app.database.session import get_db, get_session_scope
from app.evidence import anchoring, service, timestamping
from app.evidence.schemas import AnchorOut, EvidenceOut, HashOnlyRequest
from app.evidence.upload import (
    InvalidUploadError,
    UploadTooLargeError,
    clean_filename,
    clean_media_type,
    receive_upload,
)
from app.reports.manifest import (
    EvidenceNotExportableError,
    build_manifest,
    collect_valid_timestamps,
)
from app.storage import Storage, get_storage
from app.timestamp.roots import get_trust_roots
from app.timestamp.service import get_timestamp_provider

router = APIRouter(prefix="/evidence", tags=["evidence"])

Db = Annotated[Session, Depends(get_db)]
StorageDep = Annotated[Storage, Depends(get_storage)]
ProviderDep = Annotated[object, Depends(get_timestamp_provider)]
RootsDep = Annotated[tuple, Depends(get_trust_roots)]
SessionScopeDep = Annotated[object, Depends(get_session_scope)]


def _schedule_timestamp(
    background: BackgroundTasks,
    evidence_id,
    *,
    session_scope,
    provider,
    storage,
    roots,
    actor_id,
    client,
) -> None:
    """Horodatage lancé après l'envoi de la réponse (la preuve est déjà enregistrée)."""
    if get_settings().timestamp_on_deposit:
        background.add_task(
            timestamping.timestamp_in_background,
            session_scope,
            evidence_id,
            provider=provider,
            storage=storage,
            trust_roots=roots,
            actor_id=actor_id,
            client=client,
        )


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
    background: BackgroundTasks,
    provider: ProviderDep,
    roots: RootsDep,
    session_scope: SessionScopeDep,
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
    _schedule_timestamp(
        background,
        view.evidence.id,
        session_scope=session_scope,
        provider=provider,
        storage=storage,
        roots=roots,
        actor_id=user_id,
        client=client,
    )
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
    storage: StorageDep,
    background: BackgroundTasks,
    provider: ProviderDep,
    roots: RootsDep,
    session_scope: SessionScopeDep,
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
    _schedule_timestamp(
        background,
        view.evidence.id,
        session_scope=session_scope,
        provider=provider,
        storage=storage,
        roots=roots,
        actor_id=user.id,
        client=client,
    )
    return EvidenceOut.from_view(view)


@router.post(
    "/{evidence_id}/timestamp",
    response_model=EvidenceOut,
    responses={
        409: {"description": "Déjà certifiée, ou état qui ne permet pas l'horodatage"},
        502: {"description": "Jeton reçu mais refusé par la vérification"},
        503: {"description": "TSA indisponible : réessayer plus tard"},
    },
)
def timestamp_evidence(
    evidence_id: uuid.UUID,
    user: CurrentUser,
    membership: CurrentOrganization,
    db: Db,
    storage: StorageDep,
    provider: ProviderDep,
    roots: RootsDep,
    client: Client,
) -> EvidenceOut:
    """Relance l'horodatage d'une preuve en attente ou dont la tentative a échoué."""
    if service.get_for_organization(db, membership.organization.id, evidence_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    try:
        attempt = timestamping.timestamp_evidence(
            db,
            evidence_id,
            provider=provider,
            storage=storage,
            trust_roots=roots,
            actor_id=user.id,
            client=client,
        )
    except timestamping.NotTimestampableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from None
    outcome = timestamping.TimestampOutcome
    if attempt.outcome is outcome.ALREADY_CERTIFIED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Preuve déjà certifiée.")
    if attempt.outcome is outcome.TSA_UNAVAILABLE:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autorité d'horodatage indisponible : la preuve reste en attente.",
        )
    if attempt.outcome is outcome.TOKEN_INVALID:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Jeton d'horodatage refusé par la vérification : la preuve reste en attente.",
        )
    return EvidenceOut.from_view(
        service.get_for_organization(db, membership.organization.id, evidence_id)
    )


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


@router.get(
    "/{evidence_id}/manifest",
    response_class=Response,
    responses={200: {"content": {"application/json": {}}, "description": "Manifeste v1"}},
)
def get_evidence_manifest(
    evidence_id: uuid.UUID, membership: CurrentOrganization, db: Db, storage: StorageDep
) -> Response:
    """Manifeste JSON 1.1 du dossier de preuve (schéma : veritas_verifier/
    schemas/manifest-v1.1.schema.json), publié sous sa forme canonique RFC 8785 : deux appels sur
    le même dossier renvoient exactement les mêmes octets."""
    view = service.get_for_organization(db, membership.organization.id, evidence_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    try:
        manifest = build_manifest(
            view,
            custody_service.list_events(db, evidence_id),
            collect_valid_timestamps(timestamping.timestamp_records(db, evidence_id), storage),
        )
    except EvidenceNotExportableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from None
    return Response(
        content=manifest.content,
        media_type="application/json",
        headers={
            # L'empreinte du manifeste sert d'identifiant de version (cache HTTP).
            "ETag": f'"{manifest.digest}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{evidence_id}/anchor",
    response_model=AnchorOut,
    responses={
        409: {"description": "Preuve incomplète : rien à ancrer"},
        502: {"description": "Jeton reçu mais refusé par la vérification"},
        503: {"description": "TSA indisponible : la tête de chaîne n'est pas ancrée"},
    },
)
def anchor_evidence_chain(
    evidence_id: uuid.UUID,
    user: CurrentUser,
    membership: CurrentOrganization,
    db: Db,
    storage: StorageDep,
    provider: ProviderDep,
    roots: RootsDep,
    client: Client,
) -> AnchorOut:
    """Fait horodater la tête de la chaîne de possession par la TSA (ancrage), ou
    réutilise le dernier ancrage s'il couvre déjà la tête. Appelé avant un export."""
    if service.get_for_organization(db, membership.organization.id, evidence_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    try:
        attempt = anchoring.anchor_chain_head(
            db,
            evidence_id,
            provider=provider,
            storage=storage,
            trust_roots=roots,
            actor_id=user.id,
            client=client,
        )
    except anchoring.NotAnchorableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from None
    outcome = anchoring.AnchorOutcome
    if attempt.outcome is outcome.TSA_UNAVAILABLE:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autorité d'horodatage indisponible : la tête de chaîne n'est pas ancrée.",
        )
    if attempt.outcome is outcome.TOKEN_INVALID:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Jeton d'ancrage refusé par la vérification : la tête n'est pas ancrée.",
        )
    record = attempt.record
    return AnchorOut(
        status=attempt.outcome.value,
        timestamp_record_id=record.id,
        anchored_sequence_number=record.anchored_sequence_number,
        anchored_hash=record.message_imprint,
        tsa_name=record.tsa_name,
        generation_time=record.generation_time,
    )
