"""Réponses de /api/v1/evidence."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.evidence.models import EvidenceStatus, HashSource, StorageMode
from app.evidence.service import EvidenceView


class FileOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    media_type: str
    size: int
    storage_mode: StorageMode


class HashOut(BaseModel):
    algorithm: str
    digest: str
    source: HashSource
    engine_version: str
    calculated_at: datetime


class EvidenceOut(BaseModel):
    id: uuid.UUID
    title: str
    status: EvidenceStatus
    created_at: datetime
    updated_at: datetime
    file: FileOut | None
    hash: HashOut | None

    @classmethod
    def from_view(cls, view: EvidenceView) -> "EvidenceOut":
        evidence, file, hash_record = view.evidence, view.file, view.hash_record
        return cls(
            id=evidence.id,
            title=evidence.title,
            status=EvidenceStatus(evidence.status),
            created_at=evidence.created_at,
            updated_at=evidence.updated_at,
            file=FileOut(
                id=file.id,
                original_filename=file.original_filename,
                media_type=file.media_type,
                size=file.file_size,
                storage_mode=StorageMode(file.storage_mode),
            )
            if file
            else None,
            hash=HashOut(
                algorithm=hash_record.algorithm,
                digest=hash_record.digest,
                source=HashSource(hash_record.source),
                engine_version=hash_record.engine_version,
                calculated_at=hash_record.calculated_at,
            )
            if hash_record
            else None,
        )
