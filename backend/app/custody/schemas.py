"""Réponses de GET /api/v1/evidence/{id}/events."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.crypto.custody_chain import ChainVerification
from app.custody.models import CustodyEvent


class CustodyEventOut(BaseModel):
    id: uuid.UUID
    sequence_number: int
    event_type: str
    actor_id: uuid.UUID | None
    occurred_at: datetime
    event_data: dict[str, Any]
    canonicalization: str
    previous_event_hash: str | None
    event_hash: str
    # Date d'écriture en base : informative, non incluse dans l'empreinte.
    created_at: datetime

    @classmethod
    def from_model(cls, event: CustodyEvent) -> "CustodyEventOut":
        return cls.model_validate(event, from_attributes=True)


class ChainErrorOut(BaseModel):
    position: int
    code: str
    message: str


class ChainVerificationOut(BaseModel):
    """Vérification faite par le serveur au moment de la requête, avec le même code
    que le vérificateur autonome. Elle ne remplace pas la vérification par un tiers."""

    status: Literal["PASS", "FAIL"]
    checked: int
    errors: list[ChainErrorOut]

    @classmethod
    def from_result(cls, result: ChainVerification) -> "ChainVerificationOut":
        return cls(
            status=result.status,
            checked=result.checked,
            errors=[ChainErrorOut(**vars(error)) for error in result.errors],
        )


class EvidenceEventsOut(BaseModel):
    evidence_id: uuid.UUID
    events: list[CustodyEventOut]
    chain: ChainVerificationOut
