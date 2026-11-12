"""Table des résultats de vérification (migration 0001)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, sql_in


class CheckResult(StrEnum):
    """Résultat d'un contrôle obligatoire (manifeste, intégrité, possession)."""

    PASS = "PASS"  # noqa: S105 — verdict de contrôle, pas un mot de passe
    FAIL = "FAIL"


class OptionalCheckResult(StrEnum):
    """Résultat d'un contrôle qui peut manquer d'information (jamais de PASS artificiel)."""

    PASS = "PASS"  # noqa: S105 — verdict de contrôle, pas un mot de passe
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Completeness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class OverallStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationRecord(Base):
    __tablename__ = "verification_records"
    __table_args__ = (
        CheckConstraint(sql_in("manifest_status", CheckResult), name="manifest_status_check"),
        CheckConstraint(sql_in("integrity_status", CheckResult), name="integrity_status_check"),
        CheckConstraint(
            sql_in("timestamp_status", OptionalCheckResult), name="timestamp_status_check"
        ),
        CheckConstraint(
            sql_in("certificate_status", OptionalCheckResult), name="certificate_status_check"
        ),
        CheckConstraint(sql_in("custody_status", CheckResult), name="custody_status_check"),
        CheckConstraint(sql_in("completeness", Completeness), name="completeness_check"),
        CheckConstraint(sql_in("overall_status", OverallStatus), name="overall_status_check"),
        # VALID seulement si tous les contrôles obligatoires sont PASS.
        CheckConstraint(
            "overall_status <> 'VALID' OR ("
            "manifest_status = 'PASS' AND integrity_status = 'PASS' "
            "AND timestamp_status = 'PASS' AND certificate_status = 'PASS' "
            "AND custody_status = 'PASS' AND completeness = 'COMPLETE')",
            name="check",
        ),
        Index("idx_verification_evidence", "evidence_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    # Nul quand le dossier vérifié ne provient pas de cette instance de VERITAS.
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence.id"))
    verifier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    manifest_digest: Mapped[str | None] = mapped_column(CHAR(64))
    verifier_version: Mapped[str] = mapped_column(String(20))
    manifest_status: Mapped[str] = mapped_column(String(10))
    integrity_status: Mapped[str] = mapped_column(String(10))
    timestamp_status: Mapped[str] = mapped_column(String(10))
    certificate_status: Mapped[str] = mapped_column(String(10))
    custody_status: Mapped[str] = mapped_column(String(10))
    completeness: Mapped[str] = mapped_column(String(12))
    overall_status: Mapped[str] = mapped_column(String(15))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
