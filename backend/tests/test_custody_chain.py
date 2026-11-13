"""Tests unitaires de la canonicalisation RFC 8785 et du format veritas-custody-v1."""

import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.crypto.canonical import NonCanonicalValueError, canonicalize
from app.crypto.custody_chain import event_hash, event_payload, format_timestamp

MOMENT = datetime(2026, 11, 13, 0, 13, 13, 123456, tzinfo=UTC)


def _payload(**overrides):
    fields = {
        "event_id": "8c1b4e4a-0000-4000-8000-000000000001",
        "evidence_id": "8c1b4e4a-0000-4000-8000-000000000002",
        "sequence_number": 1,
        "event_type": "FILE_RECEIVED",
        "actor_id": "8c1b4e4a-0000-4000-8000-000000000003",
        "occurred_at": MOMENT,
        "data": {"digest": "ab" * 32, "size": 15},
    }
    fields.update(overrides)
    return event_payload(**fields)


# --- Canonicalisation RFC 8785 -------------------------------------------------------


def test_keys_are_sorted_and_whitespace_removed() -> None:
    assert canonicalize({"b": 1, "a": {"d": None, "c": [3, 2]}}) == (
        b'{"a":{"c":[3,2],"d":null},"b":1}'
    )


def test_rfc8785_string_escaping_example() -> None:
    """Exemple de la RFC 8785, section 3.2.2 (chaînes)."""
    # Entrée : € $ U+000F saut-de-ligne A ' B " \ \ " /
    value = "€$" + chr(0x0F) + "\nA'B" + '"' + "\\\\" + '"' + "/"
    # Sortie attendue (RFC 8785) : U+000F et le saut de ligne échappés, « / » laissé tel quel.
    expected = '"€$' + r"\u000f\nA'B\"\\\\\"/" + '"'
    assert canonicalize(value) == expected.encode()


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


def test_timestamp_is_utc_with_microseconds() -> None:
    assert format_timestamp(MOMENT) == "2026-11-13T00:13:13.123456Z"
    montreal = MOMENT.astimezone(timezone(timedelta(hours=-5)))
    assert format_timestamp(montreal) == "2026-11-13T00:13:13.123456Z"
    with pytest.raises(ValueError):
        format_timestamp(datetime(2026, 11, 13))  # sans fuseau


def test_payload_contains_exactly_the_hashed_fields() -> None:
    assert set(_payload()) == {
        "format",
        "event_id",
        "evidence_id",
        "sequence_number",
        "event_type",
        "actor_id",
        "occurred_at",
        "data",
    }
    assert _payload()["format"] == "veritas-custody-v1"


def test_first_event_hash_is_sha256_of_canonical_payload() -> None:
    payload = _payload()
    assert event_hash(None, payload) == hashlib.sha256(canonicalize(payload)).hexdigest()


def test_next_event_hash_chains_on_previous_bytes() -> None:
    previous = event_hash(None, _payload())
    payload = _payload(sequence_number=2, event_type="EXPORTED")
    expected = hashlib.sha256(bytes.fromhex(previous) + canonicalize(payload)).hexdigest()
    assert event_hash(previous, payload) == expected
    # Le même événement après un autre prédécesseur a une autre empreinte.
    assert event_hash("00" * 32, payload) != expected


@pytest.mark.parametrize(
    "change",
    [
        {"event_type": "FALSIFIED"},
        {"sequence_number": 2},
        {"actor_id": None},
        {"occurred_at": MOMENT + timedelta(microseconds=1)},
        {"data": {"digest": "ab" * 32, "size": 16}},
    ],
)
def test_any_change_in_a_hashed_field_changes_the_hash(change) -> None:
    assert event_hash(None, _payload(**change)) != event_hash(None, _payload())


def test_hash_is_deterministic_whatever_the_key_order() -> None:
    reordered = _payload(data={"size": 15, "digest": "ab" * 32})
    assert event_hash(None, reordered) == event_hash(None, _payload())
