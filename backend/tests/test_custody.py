"""Tests d'intégration de la chaîne de possession (issue #7 : T06, T07, concurrence)."""

import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.cookies import CSRF_HEADER, csrf_cookie_name
from app.crypto.custody_chain import verify_chain
from app.custody.service import CustodyEventType, append_event, list_events, to_chain_event
from app.evidence.models import Evidence
from app.main import app
from app.organizations.models import Organization
from app.storage import get_storage
from app.storage.local import LocalStorage

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"


@pytest.fixture
def storage(tmp_path: Path):
    app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path / "storage")
    yield
    app.dependency_overrides.pop(get_storage, None)


def _login(client: TestClient) -> None:
    email = f"analyste-{uuid.uuid4().hex[:8]}@exemple.test"
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
        ).status_code
        == 201
    )


def _deposit(client: TestClient) -> str:
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("journal.log", b"contenu synthetique")},
        headers={CSRF_HEADER: client.cookies.get(csrf_cookie_name())},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_history_of_a_new_evidence(api, storage) -> None:
    """T06 : l'historique est consultable et la chaîne est vérifiée."""
    _login(api)
    evidence_id = _deposit(api)

    response = api.get(f"/api/v1/evidence/{evidence_id}/events")

    assert response.status_code == 200
    body = response.json()
    assert body["evidence_id"] == evidence_id
    assert body["chain"] == {"status": "PASS", "checked": 1, "errors": []}
    [event] = body["events"]
    assert event["sequence_number"] == 1
    assert event["event_type"] == "FILE_RECEIVED"
    assert event["previous_event_hash"] is None
    assert event["canonicalization"] == "JCS-RFC8785"
    assert len(event["event_hash"]) == 64


def test_history_of_another_organization_is_404(api, storage) -> None:
    _login(api)
    evidence_id = _deposit(api)
    with TestClient(app, base_url="https://testserver") as other:
        _login(other)
        foreign = other.get(f"/api/v1/evidence/{evidence_id}/events")
        missing = other.get(f"/api/v1/evidence/{uuid.uuid4()}/events")
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()


def test_history_requires_authentication(api) -> None:
    assert api.get(f"/api/v1/evidence/{uuid.uuid4()}/events").status_code == 401


def test_chain_of_several_events_verifies_from_database(api, storage, db_session) -> None:
    """Événements ajoutés par le service, relus en base, puis vérifiés : la date relue
    (avec son fuseau PostgreSQL) redonne exactement les mêmes empreintes."""
    _login(api)
    evidence_id = uuid.UUID(_deposit(api))
    for number in range(2, 6):
        append_event(
            db_session,
            evidence_id=evidence_id,
            event_type=CustodyEventType.FILE_RECEIVED,
            actor_id=None,
            occurred_at=datetime.now(UTC),
            data={"note": f"événement {number}", "rang": number},
        )
    db_session.commit()
    db_session.expire_all()  # relire vraiment en base

    events = list_events(db_session, evidence_id)
    assert [e.sequence_number for e in events] == [1, 2, 3, 4, 5]
    assert verify_chain([to_chain_event(e) for e in events]).passed
    body = api.get(f"/api/v1/evidence/{evidence_id}/events").json()
    assert body["chain"]["status"] == "PASS"
    assert body["chain"]["checked"] == 5


def test_created_at_is_not_part_of_the_hash(api, storage, db_session) -> None:
    """created_at (date d'écriture en base) diffère de occurred_at et n'est pas haché :
    la chaîne se vérifie sans lui."""
    _login(api)
    evidence_id = uuid.UUID(_deposit(api))
    [event] = list_events(db_session, evidence_id)
    assert "created_at" not in vars(to_chain_event(event))
    assert verify_chain([to_chain_event(event)]).passed


# --- Concurrence ---------------------------------------------------------------------


def test_twenty_simultaneous_appends_get_sequences_1_to_20(app_engine) -> None:
    """Critère de l'issue #7 : 20 ajouts lancés en même temps sur la même preuve donnent
    les séquences 1 à 20, sans trou ni doublon, et une chaîne valide.

    Les ajouts sont réellement validés en base, chacun dans sa propre connexion : ces
    lignes restent dans la base de test (custody_events ne peut pas être vidée).
    """
    with Session(app_engine) as setup:
        organization = Organization(name="Test concurrence", is_personal=True)
        setup.add(organization)
        setup.flush()
        user_id = setup.execute(
            text("INSERT INTO users (email, password_hash) VALUES (:e, 'x') RETURNING id"),
            {"e": f"concurrence-{uuid.uuid4().hex[:8]}@exemple.test"},
        ).scalar_one()
        evidence = Evidence(organization_id=organization.id, owner_id=user_id, title="Concurrence")
        setup.add(evidence)
        setup.commit()
        evidence_id = evidence.id

    workers = 20
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def add_event(rank: int) -> None:
        try:
            with Session(app_engine) as session:
                barrier.wait()  # tous les fils partent en même temps
                append_event(
                    session,
                    evidence_id=evidence_id,
                    event_type=CustodyEventType.FILE_RECEIVED,
                    actor_id=user_id,
                    occurred_at=datetime.now(UTC),
                    data={"fil": rank},
                )
                session.commit()
        except BaseException as error:  # noqa: BLE001 - remonté par l'assertion ci-dessous
            errors.append(error)

    threads = [threading.Thread(target=add_event, args=(rank,)) for rank in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    with Session(app_engine) as session:
        events = list_events(session, evidence_id)
        assert [e.sequence_number for e in events] == list(range(1, workers + 1))
        assert sorted(e.event_data["fil"] for e in events) == list(range(workers))
        assert verify_chain([to_chain_event(e) for e in events]).passed
