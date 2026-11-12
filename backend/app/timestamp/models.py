"""Table des horodatages RFC 3161 (migration 0001)."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, sql_in


class TimestampPurpose(StrEnum):
    FILE = "FILE"  # horodatage de l'empreinte d'un fichier
    CHAIN_HEAD = "CHAIN_HEAD"  # horodatage de la tête de la chaîne de possession (ancrage)


class TimestampHashAlgorithm(StrEnum):
    SHA256 = "SHA-256"


class TimestampValidationStatus(StrEnum):
    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"
    ERROR = "ERROR"


class TimestampRecord(Base):
    __tablename__ = "timestamp_records"
    __table_args__ = (
        CheckConstraint(sql_in("purpose", TimestampPurpose), name="purpose_check"),
        CheckConstraint(
            sql_in("hash_algorithm", TimestampHashAlgorithm), name="hash_algorithm_check"
        ),
        CheckConstraint("message_imprint ~ '^[0-9a-f]+$'", name="message_imprint_check"),
        CheckConstraint(
            sql_in("validation_status", TimestampValidationStatus),
            name="validation_status_check",
        ),
        # Un horodatage de fichier désigne son empreinte ; un ancrage de chaîne non.
        CheckConstraint("(purpose = 'FILE') = (hash_record_id IS NOT NULL)", name="check"),
        # Un jeton déclaré valide doit exister et porter son heure de génération.
        CheckConstraint(
            "validation_status <> 'VALID' "
            "OR (token_storage_key IS NOT NULL AND generation_time IS NOT NULL)",
            name="check1",
        ),
        Index("idx_timestamp_evidence", "evidence_id"),
        Index(
            "idx_timestamp_pending",
            "validation_status",
            postgresql_where="validation_status = 'PENDING'",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence.id"))
    purpose: Mapped[str] = mapped_column(String(20))
    hash_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hash_records.id"))
    hash_algorithm: Mapped[str] = mapped_column(String(30))
    message_imprint: Mapped[str] = mapped_column(String(128))
    tsa_name: Mapped[str] = mapped_column(String(255))
    tsa_url: Mapped[str] = mapped_column(String(512))
    # Nonce RFC 3161 : entier jusqu'à 128 bits, d'où NUMERIC(40, 0) et non BIGINT.
    nonce: Mapped[Decimal | None] = mapped_column(Numeric(40, 0))
    request_storage_key: Mapped[str | None] = mapped_column(String(512))
    token_storage_key: Mapped[str | None] = mapped_column(String(512))
    policy_oid: Mapped[str | None] = mapped_column(String(255))
    serial_number: Mapped[str | None] = mapped_column(String(128))
    generation_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_status: Mapped[str] = mapped_column(
        String(20), server_default=TimestampValidationStatus.PENDING.value
    )
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
