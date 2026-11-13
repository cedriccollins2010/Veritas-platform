"""Tests unitaires : canonicalisation RFC 8785 et format veritas-custody-v1 (issue #7).

Aucun accès à la base : ces fonctions seront reprises par le vérificateur autonome.
"""

import dataclasses
import hashlib
import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
import rfc8785

from veritas_verifier.canonical import NonCanonicalValueError, canonicalize
from veritas_verifier.custody_chain import (
    GENESIS,
    ChainEvent,
    event_hash,
    event_payload,
    format_timestamp,
    verify_chain,
)

MOMENT = datetime(2026, 11, 13, 0, 13, 13, 123456, tzinfo=UTC)
EVIDENCE_ID = "8c1b4e4a-0000-4000-8000-0000000000aa"
ACTOR_ID = "8c1b4e4a-0000-4000-8000-0000000000bb"


# --- Vecteurs de test RFC 8785 --------------------------------------------------------


def test_rfc8785_section_3_2_2_example() -> None:
    """Exemple complet de la RFC 8785, section 3.2.2 (nombres, chaîne, littéraux)."""
    value = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 0.000000000000000000000000001],
        "string": "€$" + chr(0x0F) + "\nA'B" + '"' + "\\\\" + '"' + "/",
        "literals": [None, True, False],
    }
    expected = (
        '{"literals":[null,true,false],'
        '"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        '"string":"€$' + r"\u000f\nA'B\"\\\\\"/" + '"}'
    )
    assert rfc8785.dumps(value) == expected.encode()


def test_rfc8785_section_3_2_3_sorting() -> None:
    """Tri des clés par unités UTF-16 (RFC 8785, section 3.2.3)."""
    value = {
        "€": "Euro Sign",
        "\r": "Carriage Return",
        "דּ": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "😀": "Emoji: Grinning Face",
        "\u0080": "Control",
        "ö": "Latin Small Letter O With Diaeresis",
    }
    keys_in_output_order = ["\r", "1", "\u0080", "ö", "€", "😀", "דּ"]
    expected = (
        "{"
        + ",".join(
            rfc8785.dumps(k).decode() + ":" + rfc8785.dumps(value[k]).decode()
            for k in keys_in_output_order
        )
        + "}"
    )
    assert rfc8785.dumps(value) == expected.encode()


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        # RFC 8785, annexe B (sérialisation des nombres IEEE 754).
        (0.0, "0"),
        (-0.0, "0"),
        (5e-324, "5e-324"),
        (-5e-324, "-5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (-1.7976931348623157e308, "-1.7976931348623157e+308"),
        (9007199254740992.0, "9007199254740992"),
        (-9007199254740992.0, "-9007199254740992"),
        (295147905179352830000.0, "295147905179352830000"),
        (9.999999999999997e22, "9.999999999999997e+22"),
        (1e23, "1e+23"),
        (1.0000000000000001e23, "1.0000000000000001e+23"),
        (999999999999999700000.0, "999999999999999700000"),
        (999999999999999900000.0, "999999999999999900000"),
        (1e21, "1e+21"),
        (999999999999999.9, "999999999999999.9"),
        (0.000001, "0.000001"),
        (1e-7, "1e-7"),
    ],
)
def test_rfc8785_appendix_b_numbers(number: float, expected: str) -> None:
    assert rfc8785.dumps(number) == expected.encode()


def test_rfc8785_rejects_nan() -> None:
    with pytest.raises(Exception):  # noqa: B017 - l'exception exacte dépend de la bibliothèque
        rfc8785.dumps(math.nan)


# --- Règles supplémentaires de VERITAS ------------------------------------------------


def test_keys_are_sorted_and_whitespace_removed() -> None:
    assert canonicalize({"b": 1, "a": {"d": None, "c": [3, 2]}}) == (
        b'{"a":{"c":[3,2],"d":null},"b":1}'
    )


def test_unicode_is_kept_as_utf8_not_escaped() -> None:
    assert canonicalize({"nom": "Élodie"}) == '{"nom":"Élodie"}'.encode()


@pytest.mark.parametrize(
    "value",
    [{"x": 1.5}, {"x": 2**53}, {"x": b"octets"}, {1: "clé non textuelle"}, {"x": {1, 2}}],
)
def test_values_that_could_hash_differently_are_refused(value) -> None:
    with pytest.raises(NonCanonicalValueError):
        canonicalize(value)


# --- Format veritas-custody-v1 ------------------------------------------------------


def _payload(**overrides):
    fields = {
        "event_id": "8c1b4e4a-0000-4000-8000-000000000001",
        "evidence_id": EVIDENCE_ID,
        "sequence_number": 1,
        "event_type": "FILE_RECEIVED",
        "actor_id": ACTOR_ID,
        "occurred_at": MOMENT,
        "event_data": {"digest": "ab" * 32, "size": 15},
    }
    fields.update(overrides)
    return event_payload(**fields)


def test_timestamp_is_utc_with_microseconds() -> None:
    assert format_timestamp(MOMENT) == "2026-11-13T00:13:13.123456Z"
    montreal = MOMENT.astimezone(timezone(timedelta(hours=-5)))
    assert format_timestamp(montreal) == "2026-11-13T00:13:13.123456Z"
    assert format_timestamp("2026-11-13T00:13:13.123456Z") == "2026-11-13T00:13:13.123456Z"
    for bad in (datetime(2026, 11, 13), "2026-11-13T00:13:13Z", "2026-11-13 00:13:13.123456Z"):
        with pytest.raises(ValueError):
            format_timestamp(bad)


def test_payload_contains_exactly_the_hashed_fields() -> None:
    """Liste figée de l'issue #7, plus le numéro de format. created_at n'y est pas."""
    assert set(_payload()) == {
        "format",
        "event_id",
        "evidence_id",
        "sequence_number",
        "event_type",
        "actor_id",
        "occurred_at",
        "event_data",
    }
    assert _payload()["format"] == "veritas-custody-v1"


def test_first_event_is_chained_on_32_zero_bytes() -> None:
    payload = _payload()
    assert GENESIS == b"\x00" * 32
    assert event_hash(None, payload) == hashlib.sha256(GENESIS + canonicalize(payload)).hexdigest()


def test_next_event_hash_chains_on_previous_bytes() -> None:
    previous = event_hash(None, _payload())
    payload = _payload(sequence_number=2, event_type="EXPORTED")
    expected = hashlib.sha256(bytes.fromhex(previous) + canonicalize(payload)).hexdigest()
    assert event_hash(previous, payload) == expected
    assert event_hash("11" * 32, payload) != expected


@pytest.mark.parametrize(
    "change",
    [
        {"event_type": "FALSIFIED"},
        {"sequence_number": 2},
        {"actor_id": None},
        {"occurred_at": MOMENT + timedelta(microseconds=1)},
        {"event_data": {"digest": "ab" * 32, "size": 16}},
    ],
)
def test_any_change_in_a_hashed_field_changes_the_hash(change) -> None:
    assert event_hash(None, _payload(**change)) != event_hash(None, _payload())


def test_hash_is_deterministic_whatever_the_key_order() -> None:
    reordered = _payload(event_data={"size": 15, "digest": "ab" * 32})
    assert event_hash(None, reordered) == event_hash(None, _payload())


# Vecteur de référence du format v1, écrit en clair pour qui réimplémente le
# vérificateur : octets canoniques exacts de l'événement d'exemple, puis son empreinte
# SHA-256(32 octets nuls ‖ ces octets). Si ce test change, le format a changé : c'est
# interdit sans nouveau numéro de format.
KNOWN_CANONICAL = (
    '{"actor_id":"8c1b4e4a-0000-4000-8000-0000000000bb",'
    '"event_data":{"digest":"' + "ab" * 32 + '","size":15},'
    '"event_id":"8c1b4e4a-0000-4000-8000-000000000001",'
    '"event_type":"FILE_RECEIVED",'
    '"evidence_id":"8c1b4e4a-0000-4000-8000-0000000000aa",'
    '"format":"veritas-custody-v1",'
    '"occurred_at":"2026-11-13T00:13:13.123456Z",'
    '"sequence_number":1}'
)
KNOWN_FIRST_HASH = "9f6eb9a51c1e824f3d69943c1e74722b8cfbe091557c8442fea36ac3485629f2"


def test_known_answer() -> None:
    assert canonicalize(_payload()) == KNOWN_CANONICAL.encode()
    # Calcul indépendant de event_hash, avec hashlib seul :
    assert hashlib.sha256(b"\x00" * 32 + KNOWN_CANONICAL.encode()).hexdigest() == KNOWN_FIRST_HASH
    assert event_hash(None, _payload()) == KNOWN_FIRST_HASH


# --- verify_chain : chaînes valides et altérées (T07) --------------------------------


def _chain(length: int = 5) -> list[ChainEvent]:
    events: list[ChainEvent] = []
    previous = None
    for number in range(1, length + 1):
        fields = {
            "event_id": f"8c1b4e4a-0000-4000-8000-{number:012d}",
            "evidence_id": EVIDENCE_ID,
            "sequence_number": number,
            "event_type": "FILE_RECEIVED" if number == 1 else "NOTE_ADDED",
            "actor_id": ACTOR_ID,
            "occurred_at": MOMENT + timedelta(minutes=number),
            "event_data": {"note": f"événement {number}"},
        }
        current = event_hash(previous, event_payload(**fields))
        events.append(ChainEvent(**fields, previous_event_hash=previous, event_hash=current))
        previous = current
    return events


def _codes(events) -> set[str]:
    return {error.code for error in verify_chain(events).errors}


def test_valid_chain_passes() -> None:
    result = verify_chain(_chain())
    assert result.passed
    assert (result.status, result.checked, result.errors) == ("PASS", 5, [])


def test_single_event_chain_passes() -> None:
    assert verify_chain(_chain(1)).passed


def test_empty_chain_fails() -> None:
    assert _codes([]) == {"EMPTY"}


def test_modified_event_is_detected() -> None:
    events = _chain()
    events[2] = dataclasses.replace(events[2], event_data={"note": "falsifié"})
    result = verify_chain(events)
    assert not result.passed
    assert [(e.position, e.code) for e in result.errors] == [(3, "HASH_MISMATCH")]


def test_modified_date_is_detected() -> None:
    events = _chain()
    events[0] = dataclasses.replace(events[0], occurred_at=MOMENT - timedelta(days=1))
    assert _codes(events) == {"HASH_MISMATCH"}


def test_deleted_event_is_detected() -> None:
    events = _chain()
    del events[2]
    codes = _codes(events)
    assert "SEQUENCE" in codes and "BROKEN_LINK" in codes


def test_deleted_last_event_cannot_be_detected_alone() -> None:
    """Limite connue : retirer la fin de la chaîne laisse une chaîne cohérente. C'est
    l'ancrage de la tête de chaîne par la TSA (phase 3) qui le détectera."""
    assert verify_chain(_chain()[:-1]).passed


def test_swapped_events_are_detected() -> None:
    events = _chain()
    events[1], events[2] = events[2], events[1]
    codes = _codes(events)
    assert "SEQUENCE" in codes and "BROKEN_LINK" in codes


def test_swapped_and_renumbered_events_are_detected() -> None:
    """Même en renumérotant les événements inversés, les empreintes ne correspondent plus."""
    events = _chain()
    second, third = events[1], events[2]
    events[1] = dataclasses.replace(third, sequence_number=2)
    events[2] = dataclasses.replace(second, sequence_number=3)
    assert "HASH_MISMATCH" in _codes(events) or "BROKEN_LINK" in _codes(events)
    assert not verify_chain(events).passed


def test_broken_link_is_detected() -> None:
    events = _chain()
    events[3] = dataclasses.replace(events[3], previous_event_hash="00" * 32)
    codes = _codes(events)
    assert "BROKEN_LINK" in codes and "HASH_MISMATCH" in codes


def test_rewritten_suffix_is_detected_by_the_next_event() -> None:
    """Un faussaire modifie l'événement 3 et recalcule SON empreinte : l'événement 4
    désigne toujours l'ancienne, la rupture se voit."""
    events = _chain()
    forged = dataclasses.replace(events[2], event_data={"note": "falsifié"})
    forged_hash = event_hash(
        forged.previous_event_hash,
        event_payload(
            event_id=forged.event_id,
            evidence_id=forged.evidence_id,
            sequence_number=forged.sequence_number,
            event_type=forged.event_type,
            actor_id=forged.actor_id,
            occurred_at=forged.occurred_at,
            event_data=forged.event_data,
        ),
    )
    events[2] = dataclasses.replace(forged, event_hash=forged_hash)
    result = verify_chain(events)
    assert [(e.position, e.code) for e in result.errors] == [(4, "BROKEN_LINK")]


def test_first_event_with_a_predecessor_is_detected() -> None:
    events = _chain()
    events[0] = dataclasses.replace(events[0], previous_event_hash="00" * 32)
    assert "BROKEN_LINK" in _codes(events)


def test_events_from_another_evidence_are_detected() -> None:
    events = _chain()
    events[4] = dataclasses.replace(events[4], evidence_id="8c1b4e4a-0000-4000-8000-0000000000cc")
    assert {"MIXED_EVIDENCE", "HASH_MISMATCH"} <= _codes(events)


def test_malformed_values_fail_instead_of_crashing() -> None:
    events = _chain()
    events[1] = dataclasses.replace(events[1], event_hash="pas une empreinte")
    events[2] = dataclasses.replace(events[2], occurred_at="hier")
    codes = _codes(events)
    assert "HASH_MISMATCH" in codes and "UNREADABLE" in codes


def test_verification_accepts_exported_string_dates() -> None:
    """Un dossier exporté contient des dates en texte : la vérification doit aboutir
    au même résultat qu'avec des objets datetime."""
    events = [dataclasses.replace(e, occurred_at=format_timestamp(e.occurred_at)) for e in _chain()]
    assert verify_chain(events).passed
