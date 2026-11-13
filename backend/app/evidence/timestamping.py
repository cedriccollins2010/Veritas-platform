"""Horodatage d'une preuve et reprise sur panne de la TSA (issue #25).

    HASHED ──► TIMESTAMP_PENDING ──► CERTIFIED          (jeton reçu et VALID)
                      │
                      └──► reste TIMESTAMP_PENDING      (TSA en panne : ERROR ;
                                                         jeton refusé : INVALID)

Une preuve n'est CERTIFIED qu'avec un jeton vérifié VALID, conservé, et rattaché à la
chaîne de possession par un événement TIMESTAMP_ATTACHED qui porte l'empreinte du
fichier .tsr (ADR-0009 : certains octets du jeton ne sont pas couverts par sa signature ;
l'empreinte du fichier rend visible toute retouche).

Une panne de la TSA ne fait perdre ni le fichier ni l'empreinte : la preuve reste en
attente, chaque tentative est tracée dans timestamp_records et access_logs, et
l'horodatage se relance (POST /evidence/{id}/timestamp).

Concurrence : la preuve est verrouillée (SELECT ... FOR UPDATE) pendant toute la
tentative, appel à la TSA compris (borné par TSA_TIMEOUT_SECONDS). Deux tentatives
simultanées passent l'une après l'autre ; la seconde constate CERTIFIED et s'arrête.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from cryptography import x509
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AccessOutcome
from app.audit.service import AuditAction, ClientInfo, record_access
from app.crypto.custody_chain import format_timestamp
from app.crypto.timestamp_verification import verify_timestamp_token
from app.custody.service import CustodyEventType, append_event
from app.evidence.models import Evidence, EvidenceFile, EvidenceStatus, HashRecord
from app.storage import Storage
from app.timestamp.models import TimestampPurpose, TimestampRecord, TimestampValidationStatus
from app.timestamp.provider import TimestampError, TimestampProvider
from app.timestamp.service import apply_verification, store_exchange

logger = logging.getLogger(__name__)

# États depuis lesquels un horodatage peut être (re)lancé.
TIMESTAMPABLE = frozenset({EvidenceStatus.HASHED, EvidenceStatus.TIMESTAMP_PENDING})


class TimestampOutcome(StrEnum):
    CERTIFIED = "CERTIFIED"  # jeton VALID rattaché
    ALREADY_CERTIFIED = "ALREADY_CERTIFIED"  # une autre tentative l'a fait avant
    TSA_UNAVAILABLE = "TSA_UNAVAILABLE"  # panne, délai, refus : réessayer plus tard
    TOKEN_INVALID = "TOKEN_INVALID"  # noqa: S105 - jeton RFC 3161 refusé, pas un secret


class NotTimestampableError(Exception):
    """La preuve n'est pas dans un état qui permet de l'horodater."""


@dataclass(frozen=True)
class TimestampAttempt:
    outcome: TimestampOutcome
    record_id: uuid.UUID | None = None


def timestamp_evidence(
    db: Session,
    evidence_id: uuid.UUID,
    *,
    provider: TimestampProvider,
    storage: Storage,
    trust_roots: Sequence[x509.Certificate],
    actor_id: uuid.UUID | None,
    client: ClientInfo,
) -> TimestampAttempt:
    """Une tentative d'horodatage, dans une transaction validée à la fin."""
    evidence = db.execute(
        select(Evidence).where(Evidence.id == evidence_id).with_for_update()
    ).scalar_one()
    status = EvidenceStatus(evidence.status)
    if status is EvidenceStatus.CERTIFIED:
        db.commit()
        return TimestampAttempt(TimestampOutcome.ALREADY_CERTIFIED)
    if status not in TIMESTAMPABLE:
        db.commit()
        raise NotTimestampableError(f"État {status.value} : horodatage impossible.")

    hash_record = db.execute(
        select(HashRecord)
        .join(EvidenceFile, EvidenceFile.id == HashRecord.file_id)
        .where(EvidenceFile.evidence_id == evidence_id)
    ).scalar_one()
    evidence.status = EvidenceStatus.TIMESTAMP_PENDING.value
    evidence.updated_at = func.now()
    record = TimestampRecord(
        evidence_id=evidence_id,
        purpose=TimestampPurpose.FILE.value,
        hash_record_id=hash_record.id,
        hash_algorithm=hash_record.algorithm,
        message_imprint=hash_record.digest,
        tsa_name=provider.name,
        tsa_url=provider.url,
        # Horloge de l'application (et non NOW() de la base, figé pour toute la
        # transaction) : l'ordre des tentatives reste toujours défini.
        created_at=datetime.now(UTC),
    )
    db.add(record)
    db.flush()

    try:
        exchange = provider.request_timestamp(hash_record.digest)
    except TimestampError as error:
        record.validation_status = TimestampValidationStatus.ERROR.value
        record.error_detail = str(error)[:1000]
        _log(db, evidence, actor_id, client, AccessOutcome.ERROR, record.id)
        db.commit()
        logger.warning("Horodatage de %s reporté : %s", evidence_id, error)
        return TimestampAttempt(TimestampOutcome.TSA_UNAVAILABLE, record.id)

    stored = store_exchange(storage, exchange)
    record.nonce = exchange.nonce
    record.request_storage_key = stored.request_key
    record.token_storage_key = stored.response_key
    verification = verify_timestamp_token(
        exchange.response, exchange.request, hash_record.digest, trust_roots
    )
    apply_verification(record, verification)

    if not verification.valid:
        _log(db, evidence, actor_id, client, AccessOutcome.DENIED, record.id)
        db.commit()
        logger.error("Jeton refusé pour %s : %s", evidence_id, record.error_detail)
        return TimestampAttempt(TimestampOutcome.TOKEN_INVALID, record.id)

    db.flush()
    append_event(
        db,
        evidence_id=evidence_id,
        event_type=CustodyEventType.TIMESTAMP_ATTACHED,
        actor_id=actor_id,
        occurred_at=datetime.now(UTC),
        data={
            "timestamp_record_id": str(record.id),
            "purpose": TimestampPurpose.FILE.value,
            "message_imprint": hash_record.digest,
            "tsa_name": exchange.tsa_name,
            "tsa_url": exchange.tsa_url,
            "generation_time": format_timestamp(verification.generation_time),
            "serial_number": verification.serial_number,
            "policy_oid": verification.policy_oid,
            # Empreinte du fichier .tsr conservé : toute retouche du fichier se voit.
            "token_sha256": hashlib.sha256(exchange.response).hexdigest(),
        },
    )
    evidence.status = EvidenceStatus.CERTIFIED.value
    evidence.certified_at = func.now()
    _log(db, evidence, actor_id, client, AccessOutcome.SUCCESS, record.id)
    db.commit()
    return TimestampAttempt(TimestampOutcome.CERTIFIED, record.id)


def _log(db, evidence, actor_id, client, outcome, record_id) -> None:
    record_access(
        db,
        action=AuditAction.EVIDENCE_TIMESTAMP,
        outcome=outcome,
        client=client,
        user_id=actor_id,
        organization_id=evidence.organization_id,
        resource_type="timestamp_record",
        resource_id=record_id,
    )


def timestamp_in_background(
    session_scope: Callable[[], AbstractContextManager[Session]],
    evidence_id: uuid.UUID,
    *,
    provider: TimestampProvider,
    storage: Storage,
    trust_roots: Sequence[x509.Certificate],
    actor_id: uuid.UUID | None,
    client: ClientInfo,
) -> None:
    """Tâche de fond lancée après la réponse au dépôt, avec sa propre session.

    Elle ne lève jamais d'exception : en cas d'échec imprévu, la preuve reste HASHED ou
    TIMESTAMP_PENDING et l'horodatage se relance.
    """
    try:
        with session_scope() as db:
            timestamp_evidence(
                db,
                evidence_id,
                provider=provider,
                storage=storage,
                trust_roots=trust_roots,
                actor_id=actor_id,
                client=client,
            )
    except Exception:
        logger.exception("Horodatage en tâche de fond impossible pour %s", evidence_id)


def latest_file_timestamps(
    db: Session, evidence_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, TimestampRecord]:
    """Dernière tentative d'horodatage (purpose FILE) de chaque preuve."""
    if not evidence_ids:
        return {}
    rows = db.scalars(
        select(TimestampRecord)
        .where(
            TimestampRecord.evidence_id.in_(evidence_ids),
            TimestampRecord.purpose == TimestampPurpose.FILE.value,
        )
        .order_by(TimestampRecord.created_at, TimestampRecord.id)
    )
    # Ordre chronologique : la dernière tentative de chaque preuve écrase les précédentes.
    return {row.evidence_id: row for row in rows}


def timestamp_records(db: Session, evidence_id: uuid.UUID) -> list[TimestampRecord]:
    """Toutes les tentatives d'horodatage d'une preuve (fichier et ancrages)."""
    return list(
        db.scalars(
            select(TimestampRecord)
            .where(TimestampRecord.evidence_id == evidence_id)
            .order_by(TimestampRecord.created_at, TimestampRecord.id)
        )
    )
