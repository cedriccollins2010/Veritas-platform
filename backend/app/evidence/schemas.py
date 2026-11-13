"""Réponses de /api/v1/evidence."""

import unicodedata
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    # Vrai seulement si VERITAS a calculé l'empreinte lui-même sur le fichier reçu.
    # Faux en mode « empreinte seule » : l'empreinte est celle déclarée par l'analyste,
    # le serveur n'a jamais vu le fichier. L'interface et le manifeste lisent ce champ.
    verified_by_server: bool
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
                verified_by_server=HashSource(hash_record.source) is HashSource.SERVER,
                engine_version=hash_record.engine_version,
                calculated_at=hash_record.calculated_at,
            )
            if hash_record
            else None,
        )


class HashOnlyRequest(BaseModel):
    """Corps de POST /evidence/hash-only. L'empreinte est validée par la route
    (normalize_digest), pour répondre 400 à une empreinte malformée."""

    model_config = ConfigDict(extra="forbid")

    original_filename: str = Field(min_length=1, max_length=1024)
    # Entier JSON exact (I-JSON) : la taille entre dans les données hachées.
    size: int = Field(ge=0, le=2**53 - 1)
    sha256: str = Field(max_length=128)
    title: str | None = Field(default=None, max_length=255)
    media_type: str | None = Field(default=None, max_length=255)
    # Outil et version qui ont calculé l'empreinte (ex. « sha256sum 9.4 »).
    hash_tool: str | None = Field(default=None, max_length=20)

    @field_validator("title", "hash_tool")
    @classmethod
    def no_control_characters(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(unicodedata.category(c)[0] == "C" for c in value):
            raise ValueError("caractères de contrôle interdits")
        return value.strip() or None
