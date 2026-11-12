"""Table de la chaîne de possession (migration 0001).

custody_events est append-only. La base refuse UPDATE, DELETE et TRUNCATE par un
déclencheur ; les écouteurs ci-dessous refusent en plus, côté application, de
modifier ou supprimer un événement chargé par l'ORM, pour que l'erreur apparaisse
au plus tôt. Une correction s'enregistre toujours comme un nouvel événement.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

HEX_SHA256 = "'^[0-9a-f]{64}$'"


class CustodyEvent(Base):
    __tablename__ = "custody_events"
    __table_args__ = (
        CheckConstraint("sequence_number >= 1", name="sequence_number_check"),
        CheckConstraint(f"previous_event_hash ~ {HEX_SHA256}", name="previous_event_hash_check"),
        CheckConstraint(f"event_hash ~ {HEX_SHA256}", name="event_hash_check"),
        # Seul le premier événement n'a pas de prédécesseur.
        CheckConstraint("(sequence_number = 1) = (previous_event_hash IS NULL)", name="check"),
        UniqueConstraint("evidence_id", "sequence_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(80))
    sequence_number: Mapped[int] = mapped_column(BigInteger)
    # Incluse dans l'empreinte de l'événement : fixée par l'application, en UTC.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    canonicalization: Mapped[str] = mapped_column(String(30), server_default="JCS-RFC8785")
    previous_event_hash: Mapped[str | None] = mapped_column(CHAR(64))
    event_hash: Mapped[str] = mapped_column(CHAR(64))
    # Date d'écriture en base : informative, non incluse dans l'empreinte.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppendOnlyViolation(RuntimeError):
    """Tentative de modifier ou supprimer un événement de possession."""


@event.listens_for(CustodyEvent, "before_update")
def _refuse_update(_mapper, _connection, target: CustodyEvent) -> None:
    raise AppendOnlyViolation(f"custody_events est append-only : UPDATE refusé ({target.id})")


@event.listens_for(CustodyEvent, "before_delete")
def _refuse_delete(_mapper, _connection, target: CustodyEvent) -> None:
    raise AppendOnlyViolation(f"custody_events est append-only : DELETE refusé ({target.id})")
