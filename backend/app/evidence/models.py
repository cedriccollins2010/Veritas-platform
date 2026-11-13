"""Tables des preuves, de leurs fichiers et des empreintes (migration 0001).

Ce module décrit les données ; il n'implémente aucun algorithme cryptographique
(le calcul d'empreinte est dans veritas_verifier).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, sql_in


class EvidenceStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    HASHED = "HASHED"
    TIMESTAMP_PENDING = "TIMESTAMP_PENDING"
    CERTIFIED = "CERTIFIED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class StorageMode(StrEnum):
    STORED = "STORED"  # l'original est conservé dans le stockage objet
    HASH_ONLY = "HASH_ONLY"  # seule l'empreinte, calculée chez l'analyste, est enregistrée


class HashAlgorithm(StrEnum):
    SHA256 = "SHA-256"


class HashSource(StrEnum):
    SERVER = "SERVER"  # calculée par VERITAS sur le fichier reçu
    CLIENT = "CLIENT"  # mode empreinte seule


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(sql_in("status", EvidenceStatus), name="status_check"),
        # Une preuve CERTIFIED porte obligatoirement sa date de certification.
        CheckConstraint("(status = 'CERTIFIED') <= (certified_at IS NOT NULL)", name="check"),
        Index("idx_evidence_organization", "organization_id", text("created_at DESC")),
        Index("idx_evidence_owner", "owner_id"),
        Index("idx_evidence_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), server_default=EvidenceStatus.RECEIVED.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    __table_args__ = (
        CheckConstraint(sql_in("storage_mode", StorageMode), name="storage_mode_check"),
        CheckConstraint("file_size >= 0", name="file_size_check"),
        # Une clé de stockage existe si et seulement si le fichier est conservé.
        CheckConstraint("(storage_mode = 'STORED') = (storage_key IS NOT NULL)", name="check"),
        Index("idx_evidence_files_evidence", "evidence_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence.id"))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_mode: Mapped[str] = mapped_column(String(20), server_default=StorageMode.STORED.value)
    storage_key: Mapped[str | None] = mapped_column(String(512), unique=True)
    media_type: Mapped[str] = mapped_column(String(255), server_default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HashRecord(Base):
    __tablename__ = "hash_records"
    __table_args__ = (
        CheckConstraint(sql_in("algorithm", HashAlgorithm), name="algorithm_check"),
        CheckConstraint("digest ~ '^[0-9a-f]+$'", name="digest_check"),
        CheckConstraint("encoding = 'hex'", name="encoding_check"),
        CheckConstraint(sql_in("source", HashSource), name="source_check"),
        UniqueConstraint("file_id", "algorithm"),
        Index("idx_hash_digest", "digest"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_files.id"))
    algorithm: Mapped[str] = mapped_column(String(30))
    digest: Mapped[str] = mapped_column(String(128))
    encoding: Mapped[str] = mapped_column(String(10), server_default="hex")
    engine_version: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(10))
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
