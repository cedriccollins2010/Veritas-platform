"""Tests d'intégration du mode « empreinte seule » (issue #6)."""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.cookies import CSRF_HEADER, csrf_cookie_name
from app.main import app
from app.storage import get_storage
from app.storage.local import LocalStorage

pytestmark = pytest.mark.integration

HASH_ONLY = "/api/v1/evidence/hash-only"
PASSWORD = "correct horse battery staple"
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture
def storage(tmp_path: Path):
    local = LocalStorage(tmp_path / "storage")
    app.dependency_overrides[get_storage] = lambda: local
    yield local
    app.dependency_overrides.pop(get_storage, None)


def _login(client: TestClient) -> dict:
    email = f"analyste-{uuid.uuid4().hex[:8]}@exemple.test"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return response.json()


def _declare(client: TestClient, **overrides):
    body = {"original_filename": "poste42.E01", "size": 512 * 1024**3, "sha256": DIGEST}
    body.update(overrides)
    return client.post(
        HASH_ONLY, json=body, headers={CSRF_HEADER: client.cookies.get(csrf_cookie_name())}
    )


@pytest.fixture
def user(api, storage) -> dict:
    return _login(api)


def test_declared_hash_creates_hash_only_evidence(api, user, storage, db_session) -> None:
    response = _declare(
        api, title="Image du poste 42", media_type="application/x-ewf", hash_tool="sha256sum 9.4"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "HASHED"
    assert body["title"] == "Image du poste 42"
    assert body["file"]["storage_mode"] == "HASH_ONLY"
    assert body["file"]["size"] == 512 * 1024**3  # 512 Go : impossible à téléverser
    assert body["file"]["media_type"] == "application/x-ewf"
    assert body["hash"]["digest"] == DIGEST
    assert body["hash"]["source"] == "CLIENT"
    assert body["hash"]["engine_version"] == "sha256sum 9.4"

    # Rien n'a été stocké, et la base n'a pas de clé de stockage.
    assert [p for p in storage.root.rglob("*") if p.is_file()] == []
    row = db_session.execute(
        text("SELECT storage_key, storage_mode FROM evidence_files WHERE id = :i"),
        {"i": body["file"]["id"]},
    ).one()
    assert (row.storage_key, row.storage_mode) == (None, "HASH_ONLY")


def test_hash_only_is_never_presented_as_verified_by_server(api, user, tmp_path) -> None:
    """Critère de l'issue #6 : seul un fichier reçu et haché par le serveur est
    « vérifié par le serveur », à la création comme à la consultation."""
    declared = _declare(api).json()
    assert declared["hash"]["verified_by_server"] is False
    consulted = api.get(f"/api/v1/evidence/{declared['id']}").json()
    assert consulted["hash"]["verified_by_server"] is False
    listed = {e["id"]: e for e in api.get("/api/v1/evidence").json()}
    assert listed[declared["id"]]["hash"]["verified_by_server"] is False

    uploaded = api.post(
        "/api/v1/evidence",
        files={"file": ("a.txt", b"contenu")},
        headers={CSRF_HEADER: api.cookies.get(csrf_cookie_name())},
    ).json()
    assert uploaded["hash"]["source"] == "SERVER"
    assert uploaded["hash"]["verified_by_server"] is True


def test_digest_is_normalized(api, user) -> None:
    body = _declare(api, sha256=f"  {DIGEST.upper()}  ").json()
    assert body["hash"]["digest"] == DIGEST


@pytest.mark.parametrize(
    "digest",
    [
        DIGEST[:-1],  # 63 caractères
        DIGEST + "0",  # 65 caractères
        "g" * 64,  # pas hexadécimal
        "",
        DIGEST[:32],  # longueur d'un MD5
        "sha256:" + DIGEST,
    ],
)
def test_malformed_digest_is_refused_with_400(api, user, db_session, digest) -> None:
    before = db_session.execute(text("SELECT count(*) FROM evidence")).scalar_one()
    response = _declare(api, sha256=digest)
    assert response.status_code == 400
    assert db_session.execute(text("SELECT count(*) FROM evidence")).scalar_one() == before


@pytest.mark.parametrize(
    "overrides",
    [
        {"size": -1},
        {"size": 2**53},
        {"size": 1.5},
        {"original_filename": ""},
        {"title": "titre\x00nul"},
        {"hash_tool": "x" * 21},
        {"storage_key": "originals/x"},  # champ inconnu
    ],
)
def test_invalid_fields_are_refused(api, user, overrides) -> None:
    assert _declare(api, **overrides).status_code == 422


def test_filename_is_cleaned(api, user) -> None:
    body = _declare(api, original_filename="C:\\Cas\\..\\poste42.E01").json()
    assert body["file"]["original_filename"] == "poste42.E01"


def test_custody_event_records_client_origin(api, user) -> None:
    evidence_id = _declare(api, hash_tool="FTK Imager 4.7").json()["id"]
    history = api.get(f"/api/v1/evidence/{evidence_id}/events").json()
    assert history["chain"]["status"] == "PASS"
    [event] = history["events"]
    assert event["event_type"] == "HASH_DECLARED"
    assert event["event_data"]["hash_source"] == "CLIENT"
    assert event["event_data"]["storage_mode"] == "HASH_ONLY"
    assert event["event_data"]["digest"] == DIGEST
    assert event["event_data"]["hash_tool"] == "FTK Imager 4.7"


def test_hash_only_requires_csrf_and_session(api, storage) -> None:
    assert api.post(HASH_ONLY, json={}).status_code == 403  # pas de jeton CSRF
    _login(api)
    response = api.post(
        HASH_ONLY,
        json={"original_filename": "a", "size": 1, "sha256": DIGEST},
    )
    assert response.status_code == 403


def test_other_organization_cannot_see_declared_hash(api, user) -> None:
    evidence_id = _declare(api).json()["id"]
    with TestClient(app, base_url="https://testserver") as other:
        _login(other)
        assert other.get(f"/api/v1/evidence/{evidence_id}").status_code == 404
        assert other.get(f"/api/v1/evidence/{evidence_id}/events").status_code == 404


def test_creation_is_logged(api, user, db_session) -> None:
    evidence_id = _declare(api).json()["id"]
    outcome = db_session.execute(
        text(
            "SELECT outcome FROM access_logs WHERE resource_id = :i AND action = 'evidence.create'"
        ),
        {"i": evidence_id},
    ).scalar_one()
    assert outcome == "SUCCESS"
