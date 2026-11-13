"""Ajout d'événements à la chaîne de possession d'une preuve.

La chaîne n'est jamais modifiée : on ajoute un événement à la fin. Le calcul de
l'empreinte est délégué à veritas_verifier.custody_chain (format de référence).
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from veritas_verifier import canonical, custody_chain

from app.custody.models import CustodyEvent
from app.evidence.models import Evidence


class CustodyEventType(StrEnum):
    # Le fichier a été reçu, haché par le serveur et stocké.
    FILE_RECEIVED = "FILE_RECEIVED"
    # Mode « empreinte seule » : l'analyste a déclaré l'empreinte d'un fichier resté
    # sous sa garde. Le serveur ne l'a ni reçu ni haché.
    HASH_DECLARED = "HASH_DECLARED"
    # Un jeton d'horodatage RFC 3161 vérifié VALID a été rattaché à la preuve.
    TIMESTAMP_ATTACHED = "TIMESTAMP_ATTACHED"
    # La tête de chaîne a été horodatée par la TSA (ancrage). Cet événement est ajouté
    # après l'ancrage : il n'est couvert que par l'ancrage suivant.
    CHAIN_ANCHORED = "CHAIN_ANCHORED"


def append_event(
    db: Session,
    *,
    evidence_id: uuid.UUID,
    event_type: CustodyEventType,
    actor_id: uuid.UUID | None,
    occurred_at: datetime,
    data: dict[str, Any],
) -> CustodyEvent:
    """Ajoute un événement en fin de chaîne, dans la transaction en cours.

    La preuve est d'abord verrouillée (SELECT ... FOR UPDATE) jusqu'à la fin de la
    transaction : deux ajouts simultanés sur la même preuve passent l'un après l'autre
    et ne peuvent pas recevoir le même numéro de séquence ni le même prédécesseur.
    """
    db.execute(select(Evidence.id).where(Evidence.id == evidence_id).with_for_update()).one()

    last = db.scalars(
        select(CustodyEvent)
        .where(CustodyEvent.evidence_id == evidence_id)
        .order_by(CustodyEvent.sequence_number.desc())
        .limit(1)
    ).first()
    sequence_number = last.sequence_number + 1 if last else 1
    previous_hash = last.event_hash if last else None

    # L'identifiant est choisi ici, et non par la base, parce qu'il fait partie des
    # champs hachés.
    event_id = uuid.uuid4()
    payload = custody_chain.event_payload(
        event_id=str(event_id),
        evidence_id=str(evidence_id),
        sequence_number=sequence_number,
        event_type=event_type.value,
        actor_id=str(actor_id) if actor_id else None,
        occurred_at=occurred_at,
        event_data=data,
    )
    event = CustodyEvent(
        id=event_id,
        evidence_id=evidence_id,
        actor_id=actor_id,
        event_type=event_type.value,
        sequence_number=sequence_number,
        occurred_at=occurred_at,
        event_data=data,
        canonicalization=canonical.ALGORITHM,
        previous_event_hash=previous_hash,
        event_hash=custody_chain.event_hash(previous_hash, payload),
    )
    db.add(event)
    db.flush()
    return event


def list_events(db: Session, evidence_id: uuid.UUID) -> list[CustodyEvent]:
    """Événements d'une preuve, dans l'ordre de la chaîne. L'appelant a déjà vérifié
    que la preuve appartient à l'organisation de l'utilisateur."""
    return list(
        db.scalars(
            select(CustodyEvent)
            .where(CustodyEvent.evidence_id == evidence_id)
            .order_by(CustodyEvent.sequence_number)
        )
    )


def to_chain_event(event: CustodyEvent) -> custody_chain.ChainEvent:
    """Ligne de la base → événement à vérifier (sans created_at, qui n'est pas haché)."""
    return custody_chain.ChainEvent(
        event_id=str(event.id),
        evidence_id=str(event.evidence_id),
        sequence_number=event.sequence_number,
        event_type=event.event_type,
        actor_id=str(event.actor_id) if event.actor_id else None,
        occurred_at=event.occurred_at,
        event_data=event.event_data,
        previous_event_hash=event.previous_event_hash,
        event_hash=event.event_hash,
    )
