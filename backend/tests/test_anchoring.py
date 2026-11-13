"""Ancrage de la tête de chaîne par la TSA (issue #26)."""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from veritas_verifier.custody_chain import (
    ChainEvent,
    event_hash,
    event_payload,
    verify_anchor,
    verify_chain,
)
from veritas_verifier.timestamp_verification import verify_timestamp_token

from app.auth.cookies import CSRF_HEADER, csrf_cookie_name
from app.custody.service import CustodyEventType, append_event, list_events, to_chain_event
from app.main import app
from app.storage import get_storage
from app.storage.local import LocalStorage
from app.timestamp.models import TimestampRecord
from app.timestamp.roots import get_trust_roots
from app.timestamp.service import get_timestamp_provider
from tests.local_tsa import provider_for

MOMENT = datetime(2026, 11, 13, 3, 0, tzinfo=UTC)
EVIDENCE_ID = "8c1b4e4a-0000-4000-8000-0000000000aa"


# --- Vérification pure (sans base) ---------------------------------------------------------


def _chain(length: int, *, start_data: int = 0) -> list[ChainEvent]:
    events, previous = [], None
    for number in range(1, length + 1):
        fields = {
            "event_id": f"8c1b4e4a-0000-4000-8000-{number:012d}",
            "evidence_id": EVIDENCE_ID,
            "sequence_number": number,
            "event_type": "NOTE",
            "actor_id": None,
            "occurred_at": MOMENT + timedelta(minutes=number),
            "event_data": {"rang": number + start_data},
        }
        current = event_hash(previous, event_payload(**fields))
        events.append(ChainEvent(**fields, previous_event_hash=previous, event_hash=current))
        previous = current
    return events


def test_no_anchor_is_unknown_never_pass() -> None:
    result = verify_anchor(_chain(3), None, None)
    assert result.status == "UNKNOWN"
    assert not result.passed


def test_anchor_matching_the_head_passes() -> None:
    events = _chain(4)
    assert verify_anchor(events, 4, events[-1].event_hash).passed


def test_deleting_the_last_events_is_detected_by_the_anchor() -> None:
    """La limite connue de l'ADR-0005 : sans ancrage, une chaîne tronquée paraît saine."""
    events = _chain(5)
    anchored_hash = events[-1].event_hash
    truncated = events[:-2]
    assert verify_chain(truncated).passed  # la chaîne seule ne voit rien
    result = verify_anchor(truncated, 5, anchored_hash)
    assert result.status == "FAIL"
    assert "supprimés" in result.detail


def test_rewriting_the_whole_chain_is_detected_by_the_anchor() -> None:
    """Un faussaire réécrit tout et recalcule toutes les empreintes : la chaîne est
    cohérente, mais sa tête n'est plus celle qui a été horodatée."""
    original = _chain(4)
    forged = _chain(4, start_data=100)
    assert verify_chain(forged).passed
    assert verify_anchor(forged, 4, original[-1].event_hash).status == "FAIL"


def test_events_after_the_anchor_do_not_break_it() -> None:
    events = _chain(6)
    assert verify_anchor(events, 4, events[3].event_hash).passed


def test_altered_anchored_event_is_detected() -> None:
    events = _chain(4)
    anchored_hash = events[-1].event_hash
    events[-1] = dataclasses.replace(events[-1], event_hash="00" * 32)
    assert verify_anchor(events, 4, anchored_hash).status == "FAIL"


# --- Intégration --------------------------------------------------------------------------

PASSWORD = "correct horse battery staple"


@pytest.fixture
def storage(tmp_path: Path):
    local = LocalStorage(tmp_path / "storage")
    app.dependency_overrides[get_storage] = lambda: local
    yield local
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def working_tsa(api, tsa):
    app.dependency_overrides[get_timestamp_provider] = lambda: provider_for(tsa)
    app.dependency_overrides[get_trust_roots] = lambda: (tsa.root(),)
    return tsa


def _login(client: TestClient) -> None:
    email = f"analyste-{uuid.uuid4().hex[:8]}@exemple.test"
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
        ).status_code
        == 201
    )


def _csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(csrf_cookie_name())}


def _upload(client: TestClient) -> str:
    response = client.post(
        "/api/v1/evidence", files={"file": ("journal.log", b"contenu")}, headers=_csrf(client)
    )
    assert response.status_code == 201
    return response.json()["id"]


def _anchor(client: TestClient, evidence_id: str):
    return client.post(f"/api/v1/evidence/{evidence_id}/anchor", headers=_csrf(client))


def _events(client: TestClient, evidence_id: str) -> list[dict]:
    history = client.get(f"/api/v1/evidence/{evidence_id}/events").json()
    assert history["chain"]["status"] == "PASS"
    return history["events"]


@pytest.mark.integration
def test_anchor_the_head_of_the_chain(api, storage, working_tsa, db_session) -> None:
    _login(api)
    evidence_id = _upload(api)  # certifiée : FILE_RECEIVED, TIMESTAMP_ATTACHED
    head = _events(api, evidence_id)[-1]

    response = _anchor(api, evidence_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ANCHORED"
    assert body["anchored_sequence_number"] == head["sequence_number"] == 2
    assert body["anchored_hash"] == head["event_hash"]
    events = _events(api, evidence_id)
    assert [e["event_type"] for e in events][-1] == "CHAIN_ANCHORED"
    assert events[-1]["event_data"]["anchored_sequence_number"] == 2
    assert events[-1]["event_data"]["timestamp_record_id"] == body["timestamp_record_id"]

    # Le jeton conservé est valide pour l'empreinte de la tête (vérification indépendante).
    record = db_session.get(TimestampRecord, uuid.UUID(body["timestamp_record_id"]))
    assert (record.purpose, record.hash_record_id) == ("CHAIN_HEAD", None)
    with (
        storage.open(record.token_storage_key) as token,
        storage.open(record.request_storage_key) as request,
    ):
        verification = verify_timestamp_token(
            token.read(), request.read(), head["event_hash"], [working_tsa.root()]
        )
    assert verification.valid


@pytest.mark.integration
def test_second_anchor_without_new_event_is_reused(api, storage, working_tsa, db_session):
    _login(api)
    evidence_id = _upload(api)
    first = _anchor(api, evidence_id).json()
    second = _anchor(api, evidence_id).json()

    assert second["status"] == "REUSED"
    assert second["timestamp_record_id"] == first["timestamp_record_id"]
    anchors = db_session.scalars(
        select(TimestampRecord).where(
            TimestampRecord.evidence_id == uuid.UUID(evidence_id),
            TimestampRecord.purpose == "CHAIN_HEAD",
        )
    ).all()
    assert len(anchors) == 1
    types = [e["event_type"] for e in _events(api, evidence_id)]
    assert types.count("CHAIN_ANCHORED") == 1


@pytest.mark.integration
def test_new_event_requires_a_new_anchor(api, storage, working_tsa, db_session) -> None:
    _login(api)
    evidence_id = _upload(api)
    first = _anchor(api, evidence_id).json()
    append_event(
        db_session,
        evidence_id=uuid.UUID(evidence_id),
        event_type=CustodyEventType.FILE_RECEIVED,
        actor_id=None,
        occurred_at=datetime.now(UTC),
        data={"note": "nouvel événement"},
    )
    db_session.commit()

    second = _anchor(api, evidence_id).json()
    assert second["status"] == "ANCHORED"
    assert second["anchored_sequence_number"] == first["anchored_sequence_number"] + 2


@pytest.mark.integration
def test_truncation_after_anchoring_is_detected(api, storage, working_tsa, db_session):
    """De bout en bout : chaîne relue en base, fin supprimée, l'ancrage le révèle."""
    _login(api)
    evidence_id = _upload(api)
    anchor = _anchor(api, evidence_id).json()
    events = [to_chain_event(e) for e in list_events(db_session, uuid.UUID(evidence_id))]
    k, anchored = anchor["anchored_sequence_number"], anchor["anchored_hash"]

    assert verify_anchor(events, k, anchored).passed
    truncated = events[: k - 1]
    assert verify_chain(truncated).passed
    assert verify_anchor(truncated, k, anchored).status == "FAIL"


@pytest.mark.integration
def test_tsa_down_means_not_anchored(api, storage, db_session) -> None:
    _login(api)  # TSA indisponible par défaut dans les tests
    evidence_id = _upload(api)
    response = _anchor(api, evidence_id)
    assert response.status_code == 503
    assert "CHAIN_ANCHORED" not in [e["event_type"] for e in _events(api, evidence_id)]
    status = db_session.execute(
        text(
            "SELECT validation_status FROM timestamp_records "
            "WHERE evidence_id = :i AND purpose = 'CHAIN_HEAD'"
        ),
        {"i": evidence_id},
    ).scalar_one()
    assert status == "ERROR"


@pytest.mark.integration
def test_invalid_anchor_token_is_refused(api, storage, tsa, rogue_tsa) -> None:
    app.dependency_overrides[get_timestamp_provider] = lambda: provider_for(rogue_tsa)
    app.dependency_overrides[get_trust_roots] = lambda: (tsa.root(),)
    _login(api)
    evidence_id = _upload(api)
    assert _anchor(api, evidence_id).status_code == 502
    assert "CHAIN_ANCHORED" not in [e["event_type"] for e in _events(api, evidence_id)]


@pytest.mark.integration
def test_anchor_access_rules(api, storage, working_tsa, db_session) -> None:
    _login(api)
    evidence_id = _upload(api)
    assert api.post(f"/api/v1/evidence/{evidence_id}/anchor").status_code == 403  # CSRF
    with TestClient(app, base_url="https://testserver") as other:
        _login(other)
        assert _anchor(other, evidence_id).status_code == 404
    db_session.execute(
        text("UPDATE evidence SET status = 'FAILED', certified_at = NULL WHERE id = :i"),
        {"i": evidence_id},
    )
    db_session.expire_all()
    assert _anchor(api, evidence_id).status_code == 409


@pytest.mark.integration
@pytest.mark.parametrize(
    ("purpose", "anchored"),
    [("CHAIN_HEAD", None), ("FILE", 3)],
    ids=["ancrage-sans-numero", "fichier-avec-numero"],
)
def test_database_enforces_anchored_sequence(db_session, purpose, anchored) -> None:
    """Contrainte de la migration 0003 : le numéro ancré existe si et seulement si
    l'horodatage porte sur la tête de chaîne. Toutes les autres contraintes sont
    respectées, pour que ce soit bien celle-ci qui refuse."""
    from app.auth.models import User
    from app.evidence.models import Evidence, EvidenceFile, HashRecord
    from app.organizations.models import Organization

    user = User(email=f"c-{uuid.uuid4().hex[:8]}@exemple.test", password_hash="x")
    organization = Organization(name="T", is_personal=True)
    db_session.add_all([user, organization])
    db_session.flush()
    evidence = Evidence(organization_id=organization.id, owner_id=user.id, title="T")
    db_session.add(evidence)
    db_session.flush()
    file = EvidenceFile(
        evidence_id=evidence.id, original_filename="a", storage_mode="HASH_ONLY", file_size=1
    )
    db_session.add(file)
    db_session.flush()
    hash_record = HashRecord(
        file_id=file.id,
        algorithm="SHA-256",
        digest="ab" * 32,
        engine_version="t",
        source="CLIENT",
    )
    db_session.add(hash_record)
    db_session.flush()

    savepoint = db_session.begin_nested()
    db_session.add(
        TimestampRecord(
            evidence_id=evidence.id,
            purpose=purpose,
            hash_record_id=hash_record.id if purpose == "FILE" else None,
            hash_algorithm="SHA-256",
            message_imprint="ab" * 32,
            tsa_name="t",
            tsa_url="u",
            anchored_sequence_number=anchored,
        )
    )
    with pytest.raises(IntegrityError, match="timestamp_records_anchor_check"):
        db_session.flush()
    savepoint.rollback()
