"""Manifeste 1.1 : jetons d'horodatage et ancrage (issue #27)."""

import copy
import hashlib
import json
import uuid
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from app.auth.cookies import CSRF_HEADER, csrf_cookie_name
from app.core.config import get_settings
from app.crypto import manifest as manifest_crypto
from app.crypto.custody_chain import ChainEvent, verify_anchor, verify_chain
from app.crypto.timestamp_verification import verify_timestamp_token
from app.main import app
from app.storage import get_storage
from app.storage.local import LocalStorage
from app.timestamp.models import TimestampRecord
from app.timestamp.roots import get_trust_roots
from app.timestamp.service import get_timestamp_provider
from tests.local_tsa import provider_for

pytestmark = pytest.mark.integration

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "documentation/api/manifest-v1.1.schema.json").read_text(
        encoding="utf-8"
    )
)
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


def _manifest(client: TestClient, evidence_id: str) -> dict:
    response = client.get(f"/api/v1/evidence/{evidence_id}/manifest")
    assert response.status_code == 200
    document = response.json()
    jsonschema.validate(document, SCHEMA, cls=jsonschema.Draft202012Validator)
    assert manifest_crypto.digest_is_valid(document)
    return document


def test_certified_and_anchored_evidence(api, storage, working_tsa) -> None:
    _login(api)
    evidence_id = _upload(api)
    api.post(f"/api/v1/evidence/{evidence_id}/anchor", headers=_csrf(api))

    document = _manifest(api, evidence_id)

    assert document["format_version"] == "1.1"
    assert document["evidence"]["status"] == "CERTIFIED"
    file_stamp, anchor = document["timestamps"]
    assert (file_stamp["purpose"], anchor["purpose"]) == ("FILE", "CHAIN_HEAD")
    assert file_stamp["message_imprint"] == document["files"][0]["hashes"][0]["digest"]
    assert file_stamp["anchored_sequence_number"] is None
    assert anchor["anchored_sequence_number"] == 2
    assert anchor["message_imprint"] == document["custody"]["events"][1]["event_hash"]
    assert document["timestamp_status"] == {
        "file": "VALID",
        "chain_head": "ANCHORED",
        "anchored_sequence_number": 2,
        "unanchored_events": 1,  # l'événement CHAIN_ANCHORED, couvert par le prochain ancrage
    }


def test_token_digests_match_the_stored_files(api, storage, working_tsa, db_session) -> None:
    """Critère de l'issue : l'empreinte indiquée correspond au fichier .tsr conservé."""
    _login(api)
    evidence_id = _upload(api)
    [entry] = _manifest(api, evidence_id)["timestamps"]
    record = db_session.get(TimestampRecord, uuid.UUID(entry["timestamp_record_id"]))
    with storage.open(record.token_storage_key) as token:
        assert hashlib.sha256(token.read()).hexdigest() == entry["token"]["sha256"]
    with storage.open(record.request_storage_key) as request:
        assert hashlib.sha256(request.read()).hexdigest() == entry["request"]["sha256"]
    assert entry["token"]["path"] == f"timestamp/{record.id}.tsr"


def test_pending_evidence_never_looks_certified(api, storage) -> None:
    _login(api)  # TSA indisponible par défaut dans les tests
    document = _manifest(api, _upload(api))
    assert document["evidence"]["status"] == "TIMESTAMP_PENDING"
    assert document["timestamps"] == []
    assert document["timestamp_status"]["file"] == "PENDING"
    assert document["timestamp_status"]["chain_head"] == "NONE"


def test_not_timestamped_evidence(api, storage, working_tsa, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "timestamp_on_deposit", False)
    _login(api)
    document = _manifest(api, _upload(api))
    assert document["timestamp_status"] == {
        "file": "NONE",
        "chain_head": "NONE",
        "anchored_sequence_number": None,
        "unanchored_events": 1,
    }


def test_hash_only_manifest_is_valid(api, storage, working_tsa) -> None:
    _login(api)
    response = api.post(
        "/api/v1/evidence/hash-only",
        json={"original_filename": "disque.E01", "size": 10**12, "sha256": "ab" * 32},
        headers=_csrf(api),
    )
    document = _manifest(api, response.json()["id"])
    assert document["files"][0]["hashes"][0]["verified_by_server"] is False
    assert document["timestamp_status"]["file"] == "VALID"


def test_two_exports_still_identical_byte_for_byte(api, storage, working_tsa) -> None:
    _login(api)
    evidence_id = _upload(api)
    api.post(f"/api/v1/evidence/{evidence_id}/anchor", headers=_csrf(api))
    first = api.get(f"/api/v1/evidence/{evidence_id}/manifest").content
    api.post(f"/api/v1/evidence/{evidence_id}/anchor", headers=_csrf(api))  # réutilisé
    second = api.get(f"/api/v1/evidence/{evidence_id}/manifest").content
    assert first == second


def test_a_third_party_can_verify_everything_from_the_manifest(
    api, storage, working_tsa, db_session
) -> None:
    """Ce que fera le vérificateur autonome : avec le manifeste et les fichiers .tsr/.tsq
    du passeport, vérifier la chaîne, le jeton du fichier et l'ancrage, sans VERITAS."""
    _login(api)
    evidence_id = _upload(api)
    api.post(f"/api/v1/evidence/{evidence_id}/anchor", headers=_csrf(api))
    document = _manifest(api, evidence_id)

    def stored(entry, kind):  # le passeport embarquera ces fichiers
        record = db_session.get(TimestampRecord, uuid.UUID(entry["timestamp_record_id"]))
        key = record.token_storage_key if kind == "token" else record.request_storage_key
        with storage.open(key) as handle:
            data = handle.read()
        assert hashlib.sha256(data).hexdigest() == entry[kind]["sha256"]
        return data

    events = [
        ChainEvent(evidence_id=document["evidence"]["id"], **event)
        for event in document["custody"]["events"]
    ]
    assert verify_chain(events).passed
    roots = [working_tsa.root()]
    for entry in document["timestamps"]:
        verification = verify_timestamp_token(
            stored(entry, "token"), stored(entry, "request"), entry["message_imprint"], roots
        )
        assert verification.valid, entry["purpose"]
    anchor = next(e for e in document["timestamps"] if e["purpose"] == "CHAIN_HEAD")
    assert verify_anchor(
        events, anchor["anchored_sequence_number"], anchor["message_imprint"]
    ).passed
    # Et une chaîne tronquée après l'ancrage serait révélée par le manifeste lui-même.
    truncated = events[: anchor["anchored_sequence_number"] - 1]
    assert (
        verify_anchor(
            truncated, anchor["anchored_sequence_number"], anchor["message_imprint"]
        ).status
        == "FAIL"
    )


@pytest.mark.parametrize(
    "tamper",
    [
        lambda d: d["timestamps"][1].update(anchored_sequence_number=None),
        lambda d: d["timestamps"][0].update(anchored_sequence_number=1),
        lambda d: d["timestamps"][0].update(validation_status="INVALID"),
        lambda d: d["timestamp_status"].update(chain_head="NONE"),
        lambda d: d["timestamps"][0]["token"].update(path="../etc/passwd"),
    ],
    ids=[
        "ancrage-sans-numero",
        "fichier-avec-numero",
        "jeton-non-valide",
        "statut-incoherent",
        "chemin-hors-passeport",
    ],
)
def test_schema_rejects_inconsistent_manifests(api, storage, working_tsa, tamper) -> None:
    _login(api)
    evidence_id = _upload(api)
    api.post(f"/api/v1/evidence/{evidence_id}/anchor", headers=_csrf(api))
    document = copy.deepcopy(_manifest(api, evidence_id))
    tamper(document)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, SCHEMA, cls=jsonschema.Draft202012Validator)
