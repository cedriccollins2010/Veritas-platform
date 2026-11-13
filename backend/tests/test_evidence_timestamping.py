"""Horodatage d'une preuve, états et reprise sur panne de la TSA (issue #25, T04, T12)."""

import hashlib
import threading
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit.service import ClientInfo
from app.auth.cookies import CSRF_HEADER, csrf_cookie_name
from app.core.config import get_settings
from app.custody.models import CustodyEvent
from app.evidence import timestamping
from app.main import app
from app.storage import get_storage
from app.storage.local import LocalStorage
from app.timestamp.models import TimestampRecord
from app.timestamp.roots import get_trust_roots
from app.timestamp.service import get_timestamp_provider
from tests.local_tsa import provider_for

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture
def storage(tmp_path: Path):
    local = LocalStorage(tmp_path / "storage")
    app.dependency_overrides[get_storage] = lambda: local
    yield local
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def working_tsa(api, tsa):
    """Remplace la TSA indisponible des tests par la TSA locale, qui fonctionne."""
    app.dependency_overrides[get_timestamp_provider] = lambda: provider_for(tsa)
    app.dependency_overrides[get_trust_roots] = lambda: (tsa.root(),)
    yield tsa


def _login(client: TestClient) -> None:
    email = f"analyste-{uuid.uuid4().hex[:8]}@exemple.test"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201


def _csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(csrf_cookie_name())}


def _upload(client: TestClient, content: bytes = b"contenu synthetique") -> str:
    response = client.post(
        "/api/v1/evidence", files={"file": ("journal.log", content)}, headers=_csrf(client)
    )
    assert response.status_code == 201
    return response.json()["id"]


def _get(client: TestClient, evidence_id: str) -> dict:
    return client.get(f"/api/v1/evidence/{evidence_id}").json()


def _relaunch(client: TestClient, evidence_id: str):
    return client.post(f"/api/v1/evidence/{evidence_id}/timestamp", headers=_csrf(client))


def _event_types(client: TestClient, evidence_id: str) -> list[str]:
    history = client.get(f"/api/v1/evidence/{evidence_id}/events").json()
    assert history["chain"]["status"] == "PASS"
    return [event["event_type"] for event in history["events"]]


# --- Horodatage automatique après le dépôt (T04) -----------------------------------------


def test_deposit_is_certified_in_background(api, storage, working_tsa, db_session) -> None:
    _login(api)
    evidence_id = _upload(api)

    evidence = _get(api, evidence_id)
    assert evidence["status"] == "CERTIFIED"
    assert evidence["timestamp"]["status"] == "VALID"
    assert evidence["timestamp"]["tsa_name"] == "TSA de test"
    assert evidence["timestamp"]["generation_time"] is not None
    assert _event_types(api, evidence_id) == ["FILE_RECEIVED", "TIMESTAMP_ATTACHED"]

    # L'événement porte l'empreinte du fichier .tsr conservé (ADR-0009).
    record = db_session.scalars(
        select(TimestampRecord).where(TimestampRecord.evidence_id == uuid.UUID(evidence_id))
    ).one()
    with storage.open(record.token_storage_key) as token:
        token_sha256 = hashlib.sha256(token.read()).hexdigest()
    attached = api.get(f"/api/v1/evidence/{evidence_id}/events").json()["events"][1]
    assert attached["event_data"]["token_sha256"] == token_sha256
    assert attached["event_data"]["timestamp_record_id"] == str(record.id)
    certified_at = db_session.execute(
        text("SELECT certified_at FROM evidence WHERE id = :i"), {"i": evidence_id}
    ).scalar_one()
    assert certified_at is not None


def test_hash_only_evidence_is_timestamped_but_still_not_verified(api, storage, working_tsa):
    _login(api)
    response = api.post(
        "/api/v1/evidence/hash-only",
        json={"original_filename": "disque.E01", "size": 10**12, "sha256": DIGEST},
        headers=_csrf(api),
    )
    evidence = _get(api, response.json()["id"])
    assert evidence["status"] == "CERTIFIED"
    # Le jeton atteste que l'empreinte DÉCLARÉE existait à cette date, rien de plus.
    assert evidence["hash"]["verified_by_server"] is False
    assert evidence["timestamp"]["status"] == "VALID"


def test_automatic_timestamping_can_be_disabled(api, storage, working_tsa, monkeypatch):
    monkeypatch.setattr(get_settings(), "timestamp_on_deposit", False)
    _login(api)
    evidence = _get(api, _upload(api))
    assert evidence["status"] == "HASHED"
    assert evidence["timestamp"] is None


# --- T12 : TSA en panne, puis relance ------------------------------------------------------


def test_t12_tsa_down_then_relaunched(api, storage, tsa, db_session) -> None:
    _login(api)
    content = b"piece synthetique"
    evidence_id = _upload(api, content)  # TSA indisponible (défaut des tests)

    pending = _get(api, evidence_id)
    assert pending["status"] == "TIMESTAMP_PENDING"
    assert pending["timestamp"]["status"] == "ERROR"
    assert "désactivée" in pending["timestamp"]["error_detail"]
    # Ni le fichier ni l'empreinte ne sont perdus.
    assert pending["hash"]["digest"] == hashlib.sha256(content).hexdigest()
    assert any(storage.root.joinpath("originals").iterdir())

    assert _relaunch(api, evidence_id).status_code == 503  # toujours en panne
    assert _get(api, evidence_id)["status"] == "TIMESTAMP_PENDING"

    app.dependency_overrides[get_timestamp_provider] = lambda: provider_for(tsa)
    app.dependency_overrides[get_trust_roots] = lambda: (tsa.root(),)
    response = _relaunch(api, evidence_id)
    assert response.status_code == 200
    assert response.json()["status"] == "CERTIFIED"
    assert response.json()["timestamp"]["status"] == "VALID"
    assert _event_types(api, evidence_id) == ["FILE_RECEIVED", "TIMESTAMP_ATTACHED"]

    outcomes = (
        db_session.execute(
            text(
                "SELECT outcome FROM access_logs WHERE action = 'evidence.timestamp' "
                "AND organization_id = :o ORDER BY created_at"
            ),
            {"o": pending_org(db_session, evidence_id)},
        )
        .scalars()
        .all()
    )
    assert sorted(outcomes) == ["ERROR", "ERROR", "SUCCESS"]


def pending_org(db_session, evidence_id):
    return db_session.execute(
        text("SELECT organization_id FROM evidence WHERE id = :i"), {"i": evidence_id}
    ).scalar_one()


def test_relaunch_of_certified_evidence_is_refused(api, storage, working_tsa) -> None:
    _login(api)
    evidence_id = _upload(api)
    assert _get(api, evidence_id)["status"] == "CERTIFIED"
    assert _relaunch(api, evidence_id).status_code == 409


def test_invalid_token_never_certifies(api, storage, tsa, rogue_tsa, db_session) -> None:
    """Un jeton signé par une autorité non reconnue est refusé : jamais CERTIFIED."""
    app.dependency_overrides[get_timestamp_provider] = lambda: provider_for(rogue_tsa)
    app.dependency_overrides[get_trust_roots] = lambda: (tsa.root(),)
    _login(api)
    evidence_id = _upload(api)

    evidence = _get(api, evidence_id)
    assert evidence["status"] == "TIMESTAMP_PENDING"
    assert evidence["timestamp"]["status"] == "INVALID"
    assert "SIGNATURE_AND_CHAIN" in evidence["timestamp"]["error_detail"]
    assert _relaunch(api, evidence_id).status_code == 502
    assert _event_types(api, evidence_id) == ["FILE_RECEIVED"]


def test_relaunch_requires_csrf_and_respects_organizations(api, storage, working_tsa) -> None:
    _login(api)
    app.dependency_overrides[get_timestamp_provider] = lambda: provider_for(working_tsa)
    evidence_id = _upload(api)
    assert api.post(f"/api/v1/evidence/{evidence_id}/timestamp").status_code == 403
    with TestClient(app, base_url="https://testserver") as other:
        _login(other)
        assert _relaunch(other, evidence_id).status_code == 404
        assert _relaunch(other, str(uuid.uuid4())).status_code == 404


def test_failed_evidence_cannot_be_timestamped(api, storage, working_tsa, db_session) -> None:
    _login(api)
    evidence_id = _upload(api)
    db_session.execute(
        text("UPDATE evidence SET status = 'FAILED', certified_at = NULL WHERE id = :i"),
        {"i": evidence_id},
    )
    db_session.expire_all()
    assert _relaunch(api, evidence_id).status_code == 409


# --- Concurrence ----------------------------------------------------------------------------


class _SlowProvider:
    """Laisse le temps à la seconde tentative d'arriver pendant l'appel à la TSA."""

    def __init__(self, inner) -> None:
        self.inner, self.name, self.url = inner, inner.name, inner.url

    def request_timestamp(self, digest_hex: str):
        time.sleep(0.3)
        return self.inner.request_timestamp(digest_hex)


def test_two_simultaneous_attempts_attach_a_single_token(app_engine, tsa, tmp_path) -> None:
    """Critère de l'issue : deux relances simultanées ne rattachent pas deux jetons.

    Les tentatives sont réellement validées en base, chacune dans sa propre connexion :
    ces lignes restent dans la base de test (custody_events ne peut pas être vidée)."""
    from app.auth.models import User
    from app.evidence.models import Evidence, EvidenceFile, HashRecord
    from app.organizations.models import Organization

    with Session(app_engine, expire_on_commit=False) as setup:
        user = User(email=f"concurrence-{uuid.uuid4().hex[:8]}@exemple.test", password_hash="x")
        organization = Organization(name="Concurrence", is_personal=True)
        setup.add_all([user, organization])
        setup.flush()
        evidence = Evidence(
            organization_id=organization.id, owner_id=user.id, title="T", status="HASHED"
        )
        setup.add(evidence)
        setup.flush()
        file = EvidenceFile(
            evidence_id=evidence.id, original_filename="a", storage_mode="HASH_ONLY", file_size=1
        )
        setup.add(file)
        setup.flush()
        setup.add(
            HashRecord(
                file_id=file.id,
                algorithm="SHA-256",
                digest=DIGEST,
                engine_version="test",
                source="CLIENT",
            )
        )
        setup.commit()

    storage = LocalStorage(tmp_path / "storage")
    provider = _SlowProvider(provider_for(tsa))
    barrier = threading.Barrier(2)
    outcomes, errors = [], []

    def attempt() -> None:
        try:
            with Session(app_engine, expire_on_commit=False) as db:
                barrier.wait()
                result = timestamping.timestamp_evidence(
                    db,
                    evidence.id,
                    provider=provider,
                    storage=storage,
                    trust_roots=(tsa.root(),),
                    actor_id=None,
                    client=ClientInfo(ip_address=None, user_agent=None),
                )
                outcomes.append(result.outcome)
        except BaseException as error:  # noqa: BLE001 - remonté par l'assertion
            errors.append(error)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert sorted(outcomes) == [
        timestamping.TimestampOutcome.ALREADY_CERTIFIED,
        timestamping.TimestampOutcome.CERTIFIED,
    ]
    with Session(app_engine) as db:
        attached = db.scalars(
            select(CustodyEvent).where(
                CustodyEvent.evidence_id == evidence.id,
                CustodyEvent.event_type == "TIMESTAMP_ATTACHED",
            )
        ).all()
        valid = db.scalars(
            select(TimestampRecord).where(
                TimestampRecord.evidence_id == evidence.id,
                TimestampRecord.validation_status == "VALID",
            )
        ).all()
        assert len(attached) == len(valid) == 1
