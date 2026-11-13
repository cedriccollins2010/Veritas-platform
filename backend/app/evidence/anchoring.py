"""Ancrage de la tête de chaîne de possession par la TSA (issue #26).

Une chaîne conservée dans la seule base de données ne résiste pas à quelqu'un qui peut
la réécrire en entier, ou en supprimer la fin (ADR-0005, limite connue). L'ancrage fait
horodater l'empreinte de la tête de chaîne par une autorité externe : à partir de là,
supprimer ou réécrire un événement jusqu'au numéro ancré devient détectable.

Déroulement, sous verrou de la preuve (comme l'horodatage d'un fichier) :
1. si le dernier ancrage VALID couvre déjà la tête — c'est-à-dire que le seul événement
   qui le suit est son propre CHAIN_ANCHORED —, il est réutilisé (pas d'ancrage inutile) ;
2. sinon, l'empreinte de la tête est horodatée (timestamp_records, purpose CHAIN_HEAD,
   avec le numéro de séquence ancré), le jeton est vérifié ;
3. si le jeton est VALID, un événement CHAIN_ANCHORED est ajouté APRÈS l'ancrage. Il
   désigne l'ancrage, mais n'est lui-même couvert que par l'ancrage suivant.
"""

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from cryptography import x509
from sqlalchemy import select
from sqlalchemy.orm import Session
from veritas_verifier.custody_chain import format_timestamp
from veritas_verifier.hash_service import ALGORITHM
from veritas_verifier.timestamp_verification import verify_timestamp_token

from app.audit.models import AccessOutcome
from app.audit.service import AuditAction, ClientInfo, record_access
from app.custody.models import CustodyEvent
from app.custody.service import CustodyEventType, append_event, list_events
from app.evidence.models import Evidence, EvidenceStatus
from app.storage import Storage
from app.timestamp.models import TimestampPurpose, TimestampRecord, TimestampValidationStatus
from app.timestamp.provider import TimestampError, TimestampProvider
from app.timestamp.service import apply_verification, store_exchange

# Une preuve incomplète (PROCESSING, FAILED…) n'a rien à exporter, donc rien à ancrer.
ANCHORABLE = frozenset(
    {EvidenceStatus.HASHED, EvidenceStatus.TIMESTAMP_PENDING, EvidenceStatus.CERTIFIED}
)


class AnchorOutcome(StrEnum):
    ANCHORED = "ANCHORED"  # nouvel ancrage VALID
    REUSED = "REUSED"  # le dernier ancrage couvre déjà la tête
    TSA_UNAVAILABLE = "TSA_UNAVAILABLE"
    TOKEN_INVALID = "TOKEN_INVALID"  # noqa: S105 - jeton RFC 3161 refusé, pas un secret


class NotAnchorableError(Exception):
    """La preuve n'est pas dans un état qui permet de l'ancrer."""


@dataclass(frozen=True)
class AnchorAttempt:
    outcome: AnchorOutcome
    record: TimestampRecord | None = None


def latest_valid_anchor(db: Session, evidence_id: uuid.UUID) -> TimestampRecord | None:
    return db.scalars(
        select(TimestampRecord)
        .where(
            TimestampRecord.evidence_id == evidence_id,
            TimestampRecord.purpose == TimestampPurpose.CHAIN_HEAD.value,
            TimestampRecord.validation_status == TimestampValidationStatus.VALID.value,
        )
        .order_by(TimestampRecord.anchored_sequence_number.desc())
        .limit(1)
    ).first()


def _anchor_covers_head(anchor: TimestampRecord | None, events: list[CustodyEvent]) -> bool:
    """Vrai si rien de nouveau n'est arrivé depuis l'ancrage, hormis son propre
    événement CHAIN_ANCHORED."""
    if anchor is None:
        return False
    after = [e for e in events if e.sequence_number > anchor.anchored_sequence_number]
    return len(after) == 1 and (
        after[0].event_type == CustodyEventType.CHAIN_ANCHORED.value
        and after[0].event_data.get("timestamp_record_id") == str(anchor.id)
    )


def anchor_chain_head(
    db: Session,
    evidence_id: uuid.UUID,
    *,
    provider: TimestampProvider,
    storage: Storage,
    trust_roots: Sequence[x509.Certificate],
    actor_id: uuid.UUID | None,
    client: ClientInfo,
) -> AnchorAttempt:
    evidence = db.execute(
        select(Evidence).where(Evidence.id == evidence_id).with_for_update()
    ).scalar_one()
    if EvidenceStatus(evidence.status) not in ANCHORABLE:
        db.commit()
        raise NotAnchorableError(f"État {evidence.status} : aucun ancrage possible.")

    events = list_events(db, evidence_id)
    anchor = latest_valid_anchor(db, evidence_id)
    if _anchor_covers_head(anchor, events):
        db.commit()
        return AnchorAttempt(AnchorOutcome.REUSED, anchor)

    head = events[-1]
    record = TimestampRecord(
        evidence_id=evidence_id,
        purpose=TimestampPurpose.CHAIN_HEAD.value,
        hash_record_id=None,
        hash_algorithm=ALGORITHM,
        message_imprint=head.event_hash,
        anchored_sequence_number=head.sequence_number,
        tsa_name=provider.name,
        tsa_url=provider.url,
        created_at=datetime.now(UTC),
    )
    db.add(record)
    db.flush()

    try:
        exchange = provider.request_timestamp(head.event_hash)
    except TimestampError as error:
        record.validation_status = TimestampValidationStatus.ERROR.value
        record.error_detail = str(error)[:1000]
        _log(db, evidence, actor_id, client, AccessOutcome.ERROR, record.id)
        db.commit()
        return AnchorAttempt(AnchorOutcome.TSA_UNAVAILABLE, record)

    stored = store_exchange(storage, exchange)
    record.nonce = exchange.nonce
    record.request_storage_key = stored.request_key
    record.token_storage_key = stored.response_key
    verification = verify_timestamp_token(
        exchange.response, exchange.request, head.event_hash, trust_roots
    )
    apply_verification(record, verification)
    if not verification.valid:
        _log(db, evidence, actor_id, client, AccessOutcome.DENIED, record.id)
        db.commit()
        return AnchorAttempt(AnchorOutcome.TOKEN_INVALID, record)

    db.flush()
    append_event(
        db,
        evidence_id=evidence_id,
        event_type=CustodyEventType.CHAIN_ANCHORED,
        actor_id=actor_id,
        occurred_at=datetime.now(UTC),
        data={
            "timestamp_record_id": str(record.id),
            "anchored_sequence_number": head.sequence_number,
            "anchored_hash": head.event_hash,
            "tsa_name": exchange.tsa_name,
            "tsa_url": exchange.tsa_url,
            "generation_time": format_timestamp(verification.generation_time),
            "serial_number": verification.serial_number,
            "token_sha256": hashlib.sha256(exchange.response).hexdigest(),
        },
    )
    _log(db, evidence, actor_id, client, AccessOutcome.SUCCESS, record.id)
    db.commit()
    return AnchorAttempt(AnchorOutcome.ANCHORED, record)


def _log(db, evidence, actor_id, client, outcome, record_id) -> None:
    record_access(
        db,
        action=AuditAction.CHAIN_ANCHOR,
        outcome=outcome,
        client=client,
        user_id=actor_id,
        organization_id=evidence.organization_id,
        resource_type="timestamp_record",
        resource_id=record_id,
    )
