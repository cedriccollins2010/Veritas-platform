"""Empreinte d'un événement de la chaîne de possession.

    H(n) = SHA-256( H(n-1) ‖ JCS(E(n)) )

- H(n-1) : les 32 octets de l'empreinte de l'événement précédent (et rien du tout pour
  le premier événement, qui n'a pas de prédécesseur) ;
- JCS(E(n)) : la forme canonique RFC 8785 de l'événement (voir event_payload) ;
- l'empreinte est stockée et échangée en hexadécimal minuscule (64 caractères).

Chaque empreinte dépend de toutes les précédentes : modifier, supprimer ou réordonner
un événement change toutes les empreintes qui suivent, ce qui se voit.

Ce module est la définition de référence du format « veritas-custody-v1 ». Il ne
dépend d'aucun autre module de VERITAS : le vérificateur autonome l'utilisera tel quel.
Toute modification du contenu de event_payload exige un nouveau numéro de format.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.crypto.canonical import canonicalize
from app.crypto.hash_service import normalize_digest

FORMAT = "veritas-custody-v1"


def format_timestamp(moment: datetime) -> str:
    """Date UTC au format RFC 3339 avec microsecondes : « 2026-11-13T00:13:13.123456Z ».

    La précision (microseconde) est celle de TIMESTAMPTZ : la date relue en base
    redonne exactement la même chaîne, donc la même empreinte.
    """
    if moment.tzinfo is None:
        raise ValueError("Une date sans fuseau horaire est ambiguë.")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def event_payload(
    *,
    event_id: str,
    evidence_id: str,
    sequence_number: int,
    event_type: str,
    actor_id: str | None,
    occurred_at: datetime,
    data: dict[str, Any],
) -> dict[str, Any]:
    """L'événement E(n), avec exactement les champs hachés du format v1."""
    return {
        "format": FORMAT,
        "event_id": event_id,
        "evidence_id": evidence_id,
        "sequence_number": sequence_number,
        "event_type": event_type,
        "actor_id": actor_id,
        "occurred_at": format_timestamp(occurred_at),
        "data": data,
    }


def event_hash(previous_hash: str | None, payload: dict[str, Any]) -> str:
    """H(n) en hexadécimal. `previous_hash` vaut None pour le premier événement."""
    digest = hashlib.sha256()
    if previous_hash is not None:
        digest.update(bytes.fromhex(normalize_digest(previous_hash)))
    digest.update(canonicalize(payload))
    return digest.hexdigest()
