"""Tests du manifeste JSON v1 (issue #8)."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.cookies import CSRF_HEADER, csrf_cookie_name
from app.crypto import canonical
from app.crypto import manifest as manifest_crypto
from app.crypto.custody_chain import ChainEvent, verify_chain
from app.custody.service import CustodyEventType, append_event
from app.main import app
from app.storage import get_storage
from app.storage.local import LocalStorage

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "documentation/api/manifest-v1.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
PASSWORD = "correct horse battery staple"
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_schema_is_a_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


# --- Empreinte du manifeste (sans base de données) ------------------------------------


def _sample() -> dict:
    return manifest_crypto.seal({"format": "veritas-manifest", "evidence": {"title": "Disque"}})


def test_seal_and_check() -> None:
    sealed = _sample()
    body = {k: v for k, v in sealed.items() if k != "manifest_digest"}
    expected = hashlib.sha256(canonical.canonicalize(body)).hexdigest()
    assert sealed["manifest_digest"]["value"] == expected
    assert manifest_crypto.digest_is_valid(sealed)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda m: m["evidence"].update(title="Disquf"),
        lambda m: m.update(format="veritas-manifesu"),
        lambda m: m["manifest_digest"].update(value="0" * 64),
        lambda m: m["manifest_digest"].update(algorithm="MD5"),
        lambda m: m.pop("manifest_digest"),
        lambda m: m.update(extra=None),
    ],
)
def test_tampering_invalidates_digest(tamper) -> None:
    sealed = _sample()
    tamper(sealed)
    assert not manifest_crypto.digest_is_valid(sealed)


# --- Manifeste produit par l'API -------------------------------------------------------


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


def _csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(csrf_cookie_name())}


def _upload(client: TestClient) -> str:
    response = client.post(
        "/api/v1/evidence", files={"file": ("journal.log", b"contenu")}, headers=_csrf(client)
    )
    assert response.status_code == 201
    return response.json()["id"]


def _declare(client: TestClient) -> str:
    response = client.post(
        "/api/v1/evidence/hash-only",
        json={"original_filename": "disque.E01", "size": 10**12, "sha256": DIGEST},
        headers=_csrf(client),
    )
    assert response.status_code == 201
    return response.json()["id"]


def _manifest(client: TestClient, evidence_id: str):
    return client.get(f"/api/v1/evidence/{evidence_id}/manifest")


@pytest.fixture
def logged_in(api, storage):
    _login(api)
    return api


@pytest.mark.integration
@pytest.mark.parametrize("create", [_upload, _declare], ids=["fichier", "empreinte-seule"])
def test_manifest_is_valid_against_schema(logged_in, create) -> None:
    response = _manifest(logged_in, create(logged_in))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    document = response.json()
    jsonschema.validate(document, SCHEMA, cls=jsonschema.Draft202012Validator)
    assert manifest_crypto.digest_is_valid(document)
    assert response.headers["etag"] == f'"{document["manifest_digest"]["value"]}"'


@pytest.mark.integration
def test_manifest_is_published_in_canonical_form(logged_in) -> None:
    response = _manifest(logged_in, _upload(logged_in))
    assert response.content == canonical.canonicalize(response.json())


@pytest.mark.integration
def test_two_exports_are_identical_byte_for_byte(logged_in) -> None:
    evidence_id = _upload(logged_in)
    first = _manifest(logged_in, evidence_id).content
    _upload(logged_in)  # activité sans rapport entre les deux exports
    second = _manifest(logged_in, evidence_id).content
    assert first == second


@pytest.mark.integration
def test_changing_one_character_invalidates_the_digest(logged_in) -> None:
    """Critère de l'issue : un seul caractère changé, n'importe où dans une valeur."""
    content = _manifest(logged_in, _upload(logged_in)).content.decode()
    document = json.loads(content)
    digest_value = document["manifest_digest"]["value"]
    targets = [
        document["evidence"]["title"],
        document["files"][0]["hashes"][0]["digest"],
        document["custody"]["head_hash"],
        document["custody"]["events"][0]["occurred_at"],
        document["files"][0]["original_filename"],
    ]
    for target in targets:
        position = content.index(target)
        original = content[position]
        replacement = "0" if original != "0" else "1"
        tampered = json.loads(content[:position] + replacement + content[position + 1 :])
        assert tampered["manifest_digest"]["value"] == digest_value
        assert not manifest_crypto.digest_is_valid(tampered), target


@pytest.mark.integration
def test_hash_only_manifest_says_not_verified_by_server(logged_in) -> None:
    document = _manifest(logged_in, _declare(logged_in)).json()
    [file] = document["files"]
    assert file["storage_mode"] == "HASH_ONLY"
    assert file["hashes"][0]["source"] == "CLIENT"
    assert file["hashes"][0]["verified_by_server"] is False
    assert document["custody"]["events"][0]["event_type"] == "HASH_DECLARED"


@pytest.mark.integration
def test_a_third_party_can_verify_the_chain_from_the_manifest_alone(logged_in, db_session):
    """Ce que fera le vérificateur autonome : reconstruire la chaîne à partir du seul
    manifeste (dates en texte) et la vérifier, sans accès à VERITAS."""
    evidence_id = _upload(logged_in)
    for rank in range(3):
        append_event(
            db_session,
            evidence_id=uuid.UUID(evidence_id),
            event_type=CustodyEventType.FILE_RECEIVED,
            actor_id=None,
            occurred_at=datetime.now(UTC),
            data={"rang": rank},
        )
    db_session.commit()

    document = _manifest(logged_in, evidence_id).json()
    custody = document["custody"]
    events = [
        ChainEvent(evidence_id=document["evidence"]["id"], **event) for event in custody["events"]
    ]
    assert custody["event_count"] == len(events) == 4
    assert custody["head_hash"] == events[-1].event_hash
    assert verify_chain(events).passed

    # Une modification du manifeste (même avec une empreinte recalculée) casse la chaîne.
    custody["events"][1]["event_data"] = {"rang": 99}
    forged = manifest_crypto.seal(document)
    assert manifest_crypto.digest_is_valid(forged)
    events = [
        ChainEvent(evidence_id=forged["evidence"]["id"], **event)
        for event in forged["custody"]["events"]
    ]
    assert not verify_chain(events).passed


@pytest.mark.integration
def test_manifest_of_another_organization_is_404(logged_in) -> None:
    evidence_id = _upload(logged_in)
    with TestClient(app, base_url="https://testserver") as other:
        _login(other)
        foreign = _manifest(other, evidence_id)
        missing = _manifest(other, str(uuid.uuid4()))
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()


@pytest.mark.integration
def test_failed_evidence_has_no_manifest(logged_in, db_session) -> None:
    evidence_id = _upload(logged_in)
    db_session.execute(
        text("UPDATE evidence SET status = 'FAILED' WHERE id = :i"), {"i": evidence_id}
    )
    response = _manifest(logged_in, evidence_id)
    assert response.status_code == 409


@pytest.mark.integration
def test_manifest_requires_authentication(api) -> None:
    assert _manifest(api, str(uuid.uuid4())).status_code == 401
