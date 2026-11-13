"""Création et consultation des preuves.

Ce module n'implémente aucun algorithme cryptographique : l'empreinte vient de
veritas_verifier (calculée pendant la réception), la chaîne de possession de app.custody.

Création d'une preuve, en deux transactions :
1. La preuve est enregistrée à l'état PROCESSING et validée. Si la suite échoue, il en
   reste une trace explicite (état FAILED) plutôt qu'un dépôt qui disparaît.
2. Le fichier est stocké, puis le fichier, l'empreinte et le premier événement de
   possession sont enregistrés et la preuve passe à HASHED, en une seule transaction :
   soit tout est enregistré, soit rien.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from veritas_verifier.hash_service import ALGORITHM, ENGINE_VERSION, digests_match, sha256_stream

from app.audit.models import AccessOutcome
from app.audit.service import AuditAction, ClientInfo, record_access
from app.custody.service import CustodyEventType, append_event
from app.evidence.models import (
    Evidence,
    EvidenceFile,
    EvidenceStatus,
    HashRecord,
    HashSource,
    StorageMode,
)
from app.evidence.upload import ReceivedUpload
from app.storage import Storage, new_storage_key
from app.timestamp.models import TimestampRecord

logger = logging.getLogger(__name__)


class EvidenceCreationError(Exception):
    """Le dépôt a échoué après l'enregistrement de la preuve ; elle est marquée FAILED."""

    def __init__(self, evidence_id: uuid.UUID) -> None:
        super().__init__(f"Échec du dépôt de la preuve {evidence_id}")
        self.evidence_id = evidence_id


@dataclass(frozen=True)
class EvidenceView:
    """Une preuve avec son fichier et son empreinte (absents si le dépôt a échoué)."""

    evidence: Evidence
    file: EvidenceFile | None
    hash_record: HashRecord | None
    # Dernière tentative d'horodatage du fichier, s'il y en a une.
    timestamp_record: "TimestampRecord | None" = None


def create_from_upload(
    db: Session,
    storage: Storage,
    upload: ReceivedUpload,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    client: ClientInfo,
) -> EvidenceView:
    evidence = Evidence(
        organization_id=organization_id,
        owner_id=user_id,
        title=upload.title or upload.original_filename,
        status=EvidenceStatus.PROCESSING.value,
    )
    db.add(evidence)
    db.commit()
    evidence_id = evidence.id
    storage_key: str | None = None
    stored = False

    try:
        storage_key = new_storage_key()
        with upload.path.open("rb") as stream:
            stored_size = storage.save_stream(storage_key, stream)
        stored = True
        if stored_size != upload.size:
            raise OSError(f"Taille stockée {stored_size} ≠ taille reçue {upload.size}")
        # Vérification après copie, comme un outil d'acquisition forensique : on relit
        # l'original dans le stockage et on recalcule son empreinte. L'état HASHED
        # garantit ainsi que le fichier conservé est exactement celui qui a été haché.
        with storage.open(storage_key) as stored_stream:
            stored_digest = sha256_stream(stored_stream)
        if not digests_match(upload.sha256, stored_digest):
            raise OSError("L'empreinte du fichier stocké diffère de celle de la réception.")

        evidence_file = EvidenceFile(
            evidence_id=evidence.id,
            original_filename=upload.original_filename,
            storage_mode=StorageMode.STORED.value,
            storage_key=storage_key,
            media_type=upload.media_type,
            file_size=upload.size,
        )
        db.add(evidence_file)
        db.flush()
        hash_record = HashRecord(
            file_id=evidence_file.id,
            algorithm=ALGORITHM,
            digest=upload.sha256,
            engine_version=ENGINE_VERSION,
            source=HashSource.SERVER.value,
        )
        db.add(hash_record)
        db.flush()
        append_event(
            db,
            evidence_id=evidence.id,
            event_type=CustodyEventType.FILE_RECEIVED,
            actor_id=user_id,
            occurred_at=upload.received_at,
            data={
                "file_id": str(evidence_file.id),
                "original_filename": upload.original_filename,
                "media_type": upload.media_type,
                "size": upload.size,
                "hash_algorithm": ALGORITHM,
                "digest": upload.sha256,
                "storage_mode": StorageMode.STORED.value,
                "hash_source": HashSource.SERVER.value,
            },
        )
        evidence.status = EvidenceStatus.HASHED.value
        evidence.updated_at = func.now()
        record_access(
            db,
            action=AuditAction.EVIDENCE_CREATE,
            outcome=AccessOutcome.SUCCESS,
            client=client,
            user_id=user_id,
            organization_id=organization_id,
            resource_type="evidence",
            resource_id=evidence.id,
        )
        db.commit()
    except Exception as error:
        db.rollback()
        # La cause est journalisée côté serveur ; le client ne reçoit qu'un message
        # générique. Si le fichier a déjà été stocké, sa clé est notée : il n'est
        # rattaché à aucune ligne (un fichier stocké n'est jamais supprimé).
        logger.exception(
            "Échec du dépôt de la preuve %s (fichier stocké sans référence : %s)",
            evidence_id,
            storage_key if stored else "aucun",
        )
        try:
            _mark_failed(db, evidence_id, user_id, organization_id, client)
        except Exception:
            # Par exemple, base de données injoignable : la preuve reste PROCESSING.
            db.rollback()
            logger.exception("Impossible de marquer la preuve %s comme FAILED", evidence_id)
        raise EvidenceCreationError(evidence_id) from error

    db.refresh(evidence)
    return EvidenceView(evidence=evidence, file=evidence_file, hash_record=hash_record)


@dataclass(frozen=True)
class DeclaredHash:
    """Empreinte déclarée par l'analyste, déjà validée et normalisée par l'appelant."""

    original_filename: str
    media_type: str
    size: int
    sha256: str
    title: str | None
    hash_tool: str


def create_hash_only(
    db: Session,
    declared: DeclaredHash,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    client: ClientInfo,
) -> EvidenceView:
    """Mode « empreinte seule » : enregistre l'empreinte d'un fichier qui ne quitte pas
    la garde de l'analyste. Rien n'est stocké ni recalculé par le serveur.

    Une seule transaction (pas de fichier, donc pas d'étape qui puisse échouer à moitié).
    L'origine de l'empreinte est enregistrée partout où elle compte : storage_mode =
    HASH_ONLY, hash_records.source = CLIENT, et dans l'événement de possession.
    """
    evidence = Evidence(
        organization_id=organization_id,
        owner_id=user_id,
        title=declared.title or declared.original_filename,
        status=EvidenceStatus.HASHED.value,
    )
    db.add(evidence)
    db.flush()
    evidence_file = EvidenceFile(
        evidence_id=evidence.id,
        original_filename=declared.original_filename,
        storage_mode=StorageMode.HASH_ONLY.value,
        storage_key=None,
        media_type=declared.media_type,
        file_size=declared.size,
    )
    db.add(evidence_file)
    db.flush()
    hash_record = HashRecord(
        file_id=evidence_file.id,
        algorithm=ALGORITHM,
        digest=declared.sha256,
        engine_version=declared.hash_tool,
        source=HashSource.CLIENT.value,
    )
    db.add(hash_record)
    db.flush()
    append_event(
        db,
        evidence_id=evidence.id,
        event_type=CustodyEventType.HASH_DECLARED,
        actor_id=user_id,
        occurred_at=datetime.now(UTC),
        data={
            "file_id": str(evidence_file.id),
            "original_filename": declared.original_filename,
            "media_type": declared.media_type,
            "size": declared.size,
            "hash_algorithm": ALGORITHM,
            "digest": declared.sha256,
            "storage_mode": StorageMode.HASH_ONLY.value,
            "hash_source": HashSource.CLIENT.value,
            "hash_tool": declared.hash_tool,
        },
    )
    record_access(
        db,
        action=AuditAction.EVIDENCE_CREATE,
        outcome=AccessOutcome.SUCCESS,
        client=client,
        user_id=user_id,
        organization_id=organization_id,
        resource_type="evidence",
        resource_id=evidence.id,
    )
    db.commit()
    db.refresh(evidence)
    return EvidenceView(evidence=evidence, file=evidence_file, hash_record=hash_record)


def _mark_failed(
    db: Session,
    evidence_id: uuid.UUID,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    client: ClientInfo,
) -> None:
    evidence = db.get(Evidence, evidence_id)
    evidence.status = EvidenceStatus.FAILED.value
    evidence.updated_at = func.now()
    record_access(
        db,
        action=AuditAction.EVIDENCE_CREATE,
        outcome=AccessOutcome.ERROR,
        client=client,
        user_id=user_id,
        organization_id=organization_id,
        resource_type="evidence",
        resource_id=evidence_id,
    )
    db.commit()


def _views_query(organization_id: uuid.UUID):
    # Le filtre sur l'organisation est posé ici, une seule fois, pour toutes les lectures.
    return (
        select(Evidence, EvidenceFile, HashRecord)
        .outerjoin(EvidenceFile, EvidenceFile.evidence_id == Evidence.id)
        .outerjoin(HashRecord, HashRecord.file_id == EvidenceFile.id)
        .where(Evidence.organization_id == organization_id)
    )


def list_for_organization(
    db: Session, organization_id: uuid.UUID, *, limit: int, offset: int
) -> list[EvidenceView]:
    rows = db.execute(
        _views_query(organization_id)
        .order_by(Evidence.created_at.desc(), Evidence.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return _with_timestamps(db, [EvidenceView(*row) for row in rows])


def get_for_organization(
    db: Session, organization_id: uuid.UUID, evidence_id: uuid.UUID
) -> EvidenceView | None:
    """None si la preuve n'existe pas OU appartient à une autre organisation : l'appelant
    répond 404 dans les deux cas, sans révéler qu'un identifiant existe ailleurs."""
    row = db.execute(_views_query(organization_id).where(Evidence.id == evidence_id)).first()
    return _with_timestamps(db, [EvidenceView(*row)])[0] if row else None


def _with_timestamps(db: Session, views: list[EvidenceView]) -> list[EvidenceView]:
    # Import local : timestamping dépend de ce module (EvidenceView).
    from app.evidence.timestamping import latest_file_timestamps

    latest = latest_file_timestamps(db, [view.evidence.id for view in views])
    return [
        EvidenceView(view.evidence, view.file, view.hash_record, latest.get(view.evidence.id))
        for view in views
    ]
