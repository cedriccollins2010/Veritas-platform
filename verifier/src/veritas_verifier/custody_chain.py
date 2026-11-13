"""Chaîne de possession, format « veritas-custody-v1 » : calcul et vérification.

    H(n) = SHA-256( H(n-1) ‖ JCS(E(n)) )

- H(n-1) : les 32 octets de l'empreinte de l'événement précédent ; pour le premier
  événement, 32 octets nuls (GENESIS). La formule est ainsi la même pour tous ;
- JCS(E(n)) : la forme canonique RFC 8785 de l'événement (voir event_payload) ;
- l'empreinte est stockée et échangée en hexadécimal minuscule (64 caractères).

Chaque empreinte dépend de toutes les précédentes : modifier, supprimer ou réordonner
un événement change toutes les empreintes qui suivent, ce qui se voit.

Ce module est la définition de référence du format. Il ne dépend ni du serveur VERITAS
ni d'une base de données : le serveur et le vérificateur autonome l'appellent tous deux.
Toute modification des champs hachés exige un nouveau numéro de format.
"""

import hashlib
import hmac
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from veritas_verifier.canonical import NonCanonicalValueError, canonicalize
from veritas_verifier.hash_service import normalize_digest

FORMAT = "veritas-custody-v1"
GENESIS = bytes(32)  # « H(0) » : 32 octets nuls
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")


def format_timestamp(moment: datetime | str) -> str:
    """Date UTC au format RFC 3339 avec microsecondes : « 2026-11-13T00:13:13.123456Z ».

    La précision (microseconde) est celle de TIMESTAMPTZ : la date relue en base
    redonne exactement la même chaîne, donc la même empreinte. Une chaîne déjà
    formatée (lue dans un dossier exporté) est acceptée si elle a exactement ce format.
    """
    if isinstance(moment, str):
        if not _TIMESTAMP.fullmatch(moment):
            raise ValueError(f"Date au format inattendu : {moment!r}")
        return moment
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
    occurred_at: datetime | str,
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """L'événement E(n), avec exactement les champs hachés du format v1.

    created_at (date d'écriture en base) n'en fait pas partie : seule compte la date
    de l'événement, fixée par l'application.
    """
    return {
        "format": FORMAT,
        "event_id": event_id,
        "evidence_id": evidence_id,
        "sequence_number": sequence_number,
        "event_type": event_type,
        "actor_id": actor_id,
        "occurred_at": format_timestamp(occurred_at),
        "event_data": event_data,
    }


def event_hash(previous_hash: str | None, payload: dict[str, Any]) -> str:
    """H(n) en hexadécimal. `previous_hash` vaut None pour le premier événement."""
    previous = bytes.fromhex(normalize_digest(previous_hash)) if previous_hash else GENESIS
    return hashlib.sha256(previous + canonicalize(payload)).hexdigest()


# --- Vérification ---------------------------------------------------------------------


@dataclass(frozen=True)
class ChainEvent:
    """Un événement tel qu'il est enregistré (en base ou dans un dossier exporté)."""

    event_id: str
    evidence_id: str
    sequence_number: int
    event_type: str
    actor_id: str | None
    occurred_at: datetime | str
    event_data: dict[str, Any]
    previous_event_hash: str | None
    event_hash: str


@dataclass(frozen=True)
class ChainError:
    position: int  # rang dans la liste reçue, à partir de 1
    code: str
    message: str


@dataclass(frozen=True)
class ChainVerification:
    """Résultat : PASS seulement si aucune erreur. Toutes les erreurs sont listées."""

    status: str  # "PASS" ou "FAIL"
    checked: int
    errors: list[ChainError] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def _same_digest(expected: str | None, actual: str | None) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    try:
        return hmac.compare_digest(normalize_digest(expected), normalize_digest(actual))
    except ValueError:
        return False


def verify_chain(events: Sequence[ChainEvent]) -> ChainVerification:
    """Vérifie une chaîne complète, dans l'ordre où elle est donnée.

    Fonction pure : aucun accès à la base, au réseau ou à l'horloge. Elle contrôle :
    - que la chaîne n'est pas vide et concerne une seule preuve ;
    - que les numéros de séquence vont de 1 à n sans trou ni doublon, dans l'ordre
      (détecte suppression et réordonnancement) ;
    - que chaque événement désigne bien le précédent (détecte une rupture) ;
    - que chaque empreinte recalculée est celle enregistrée (détecte une modification).
    """
    errors: list[ChainError] = []
    if not events:
        return ChainVerification("FAIL", 0, [ChainError(0, "EMPTY", "Chaîne vide.")])

    evidence_ids = {event.evidence_id for event in events}
    if len(evidence_ids) > 1:
        errors.append(ChainError(0, "MIXED_EVIDENCE", "Événements de plusieurs preuves."))
    if len({event.event_id for event in events}) != len(events):
        errors.append(ChainError(0, "DUPLICATE_EVENT", "Identifiant d'événement en double."))

    previous: ChainEvent | None = None
    for position, event in enumerate(events, start=1):
        if event.sequence_number != position:
            errors.append(
                ChainError(
                    position,
                    "SEQUENCE",
                    f"Numéro de séquence {event.sequence_number}, attendu {position}.",
                )
            )
        expected_previous = previous.event_hash if previous else None
        if not _same_digest(expected_previous, event.previous_event_hash):
            errors.append(
                ChainError(position, "BROKEN_LINK", "Ne désigne pas l'événement précédent.")
            )
        try:
            recomputed = event_hash(
                event.previous_event_hash,
                event_payload(
                    event_id=event.event_id,
                    evidence_id=event.evidence_id,
                    sequence_number=event.sequence_number,
                    event_type=event.event_type,
                    actor_id=event.actor_id,
                    occurred_at=event.occurred_at,
                    event_data=event.event_data,
                ),
            )
        except (ValueError, NonCanonicalValueError) as error:
            errors.append(ChainError(position, "UNREADABLE", f"Événement illisible : {error}"))
        else:
            if not _same_digest(recomputed, event.event_hash):
                errors.append(
                    ChainError(position, "HASH_MISMATCH", "Empreinte recalculée différente.")
                )
        previous = event

    return ChainVerification("FAIL" if errors else "PASS", len(events), errors)


# --- Ancrage de la tête de chaîne ----------------------------------------------------


@dataclass(frozen=True)
class AnchorVerification:
    """Résultat de la vérification d'un ancrage.

    PASS : la chaîne contient l'événement ancré et son empreinte est celle qui a été
    horodatée. FAIL : événements supprimés ou chaîne réécrite. UNKNOWN : aucun ancrage
    n'est fourni (la tête n'a pas été ancrée) — jamais présenté comme un PASS.
    """

    status: str  # "PASS", "FAIL" ou "UNKNOWN"
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def verify_anchor(
    events: Sequence[ChainEvent],
    anchored_sequence_number: int | None,
    anchored_hash: str | None,
) -> AnchorVerification:
    """Vérifie que la chaîne `events` est cohérente avec un ancrage.

    L'ancrage dit : « l'événement n° k avait l'empreinte H, et H existait à la date du
    jeton ». Si la chaîne n'a plus d'événement n° k (suppression en fin de chaîne), ou
    si son empreinte n'est plus H (réécriture, même avec des empreintes recalculées),
    l'ancrage le révèle. Cette fonction ne vérifie pas le jeton lui-même : c'est le rôle
    de verify_timestamp_token, avec H comme empreinte attendue.
    """
    if anchored_sequence_number is None or anchored_hash is None:
        return AnchorVerification("UNKNOWN", "La tête de chaîne n'a pas été ancrée.")
    anchored = next((e for e in events if e.sequence_number == anchored_sequence_number), None)
    if anchored is None:
        return AnchorVerification(
            "FAIL",
            f"L'événement ancré n° {anchored_sequence_number} est absent : "
            "des événements ont été supprimés.",
        )
    if not _same_digest(anchored.event_hash, anchored_hash):
        return AnchorVerification(
            "FAIL", "L'empreinte de l'événement ancré ne correspond pas à l'ancrage."
        )
    return AnchorVerification("PASS")
