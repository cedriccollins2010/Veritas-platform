"""Tests d'intégration du dépôt de preuves (issue #5 : T01, T02, T10, T11)."""

import hashlib
import io
import re
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from veritas_verifier.custody_chain import event_hash, event_payload

from app.auth.cookies import CSRF_HEADER, csrf_cookie_name
from app.core.config import get_settings
from app.custody.models import CustodyEvent
from app.evidence.models import Evidence, EvidenceFile, HashRecord
from app.main import app
from app.storage import get_storage
from app.storage.local import LocalStorage

pytestmark = pytest.mark.integration

EVIDENCE = "/api/v1/evidence"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def storage(tmp_path: Path) -> Iterator[LocalStorage]:
    local = LocalStorage(tmp_path / "storage")
    app.dependency_overrides[get_storage] = lambda: local
    yield local
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_temp_dir", directory)
    return directory


def _login(client: TestClient) -> dict:
    email = f"analyste-{uuid.uuid4().hex[:8]}@exemple.test"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return response.json()


def _csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(csrf_cookie_name())}


def _upload(client: TestClient, content: bytes, filename: str = "capture.pcap", **form):
    return client.post(
        EVIDENCE,
        files={"file": (filename, content, form.pop("media_type", "application/octet-stream"))},
        data=form,
        headers=_csrf(client),
    )


def _stored_files(storage: LocalStorage) -> list[Path]:
    return [p for p in storage.root.rglob("*") if p.is_file() and ".incoming" not in p.parts]


@pytest.fixture
def user(api, storage, upload_dir) -> dict:
    return _login(api)


# --- T01 / T02 : dépôt et empreinte --------------------------------------------------


def test_upload_creates_hashed_evidence(api, user, storage, upload_dir, db_session) -> None:
    content = b"journal synthetique\n" * 1000
    response = _upload(api, content, "journal.log", title="Journal du pare-feu")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "HASHED"
    assert body["title"] == "Journal du pare-feu"
    assert body["file"] == {
        "id": body["file"]["id"],
        "original_filename": "journal.log",
        "media_type": "application/octet-stream",
        "size": len(content),
        "storage_mode": "STORED",
    }
    assert body["hash"]["algorithm"] == "SHA-256"
    assert body["hash"]["source"] == "SERVER"
    assert body["hash"]["digest"] == hashlib.sha256(content).hexdigest()

    # L'original est conservé à l'identique (T01), et le fichier temporaire est supprimé.
    [stored] = _stored_files(storage)
    assert stored.read_bytes() == content
    assert list(upload_dir.iterdir()) == []

    row = db_session.execute(
        text("SELECT organization_id, owner_id FROM evidence WHERE id = :id"), {"id": body["id"]}
    ).one()
    assert str(row.organization_id) == user["organization"]["id"]
    assert str(row.owner_id) == user["user"]["id"]


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="sha256sum absent")
def test_digest_matches_sha256sum(api, user, tmp_path) -> None:
    content = bytes(range(256)) * 4096 + b"fin"
    sample = tmp_path / "echantillon.bin"
    sample.write_bytes(content)
    expected = subprocess.run(  # noqa: S603 - outil système, argument contrôlé
        ["sha256sum", str(sample)],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()[0]
    assert _upload(api, content).json()["hash"]["digest"] == expected


def test_empty_file_is_accepted(api, user) -> None:
    body = _upload(api, b"").json()
    assert body["file"]["size"] == 0
    assert body["hash"]["digest"] == hashlib.sha256(b"").hexdigest()


def test_title_defaults_to_filename_and_path_is_stripped(api, user, storage) -> None:
    body = _upload(api, b"x", filename="../../etc/passwd").json()
    assert body["title"] == "passwd"
    assert body["file"]["original_filename"] == "passwd"
    # Le nom fourni ne sert jamais de chemin : la clé est générée par le serveur.
    [stored] = _stored_files(storage)
    assert stored.parent.name == "originals"
    uuid.UUID(stored.name)


def test_content_is_never_interpreted(api, user, storage) -> None:
    """Un « fichier » HTML avec script est haché et stocké octet pour octet, rien de plus."""
    content = b"<html><script>alert('x')</script></html>"
    body = _upload(api, content, "page.html", media_type="text/html").json()
    assert body["file"]["media_type"] == "text/html"
    assert body["hash"]["digest"] == hashlib.sha256(content).hexdigest()
    assert _stored_files(storage)[0].read_bytes() == content


def test_first_custody_event_is_recomputable(api, user, db_session) -> None:
    """L'événement FILE_RECEIVED relu en base redonne exactement son empreinte :
    c'est ce que fera le vérificateur autonome à partir du dossier exporté."""
    body = _upload(api, b"preuve").json()
    event = db_session.execute(
        text("SELECT * FROM custody_events WHERE evidence_id = :id"), {"id": body["id"]}
    ).one()
    assert (event.sequence_number, event.event_type) == (1, "FILE_RECEIVED")
    assert event.previous_event_hash is None
    assert str(event.actor_id) == user["user"]["id"]
    assert event.event_data["digest"] == body["hash"]["digest"]
    payload = event_payload(
        event_id=str(event.id),
        evidence_id=str(event.evidence_id),
        sequence_number=event.sequence_number,
        event_type=event.event_type,
        actor_id=str(event.actor_id),
        occurred_at=event.occurred_at,
        event_data=event.event_data,
    )
    assert event_hash(None, payload) == event.event_hash


def test_upload_is_logged(api, user, db_session) -> None:
    evidence_id = _upload(api, b"x").json()["id"]
    outcome = db_session.execute(
        text(
            "SELECT outcome FROM access_logs WHERE action = 'evidence.create' AND resource_id = :i"
        ),
        {"i": evidence_id},
    ).scalar_one()
    assert outcome == "SUCCESS"


# --- T11 : taille maximale -----------------------------------------------------------


def _count(db_session, model, *conditions) -> int:
    """Nombre de lignes, par une requête SQLAlchemy (aucun SQL construit à la main)."""
    query = select(func.count()).select_from(model).where(*conditions)
    return db_session.execute(query).scalar_one()


def test_too_large_file_is_refused_without_leftovers(
    api, user, storage, upload_dir, db_session, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_size_mb", 1)
    models = (Evidence, EvidenceFile, HashRecord)
    before = {model: _count(db_session, model) for model in models}

    response = _upload(api, b"\0" * (1024 * 1024 + 1))

    assert response.status_code == 413
    assert {model: _count(db_session, model) for model in models} == before
    assert _stored_files(storage) == []
    assert list(upload_dir.iterdir()) == []


def test_file_exactly_at_the_limit_is_accepted(api, user, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_size_mb", 1)
    assert _upload(api, b"\0" * (1024 * 1024)).status_code == 201


# --- Requêtes invalides --------------------------------------------------------------


def test_upload_requires_csrf_token(api, user) -> None:
    response = api.post(EVIDENCE, files={"file": ("a.txt", b"x")})
    assert response.status_code == 403


def test_upload_requires_authentication(api, storage) -> None:
    assert api.get(EVIDENCE).status_code == 401


def test_missing_file_field(api, user) -> None:
    response = api.post(EVIDENCE, data={"title": "sans fichier"}, files={}, headers=_csrf(api))
    assert response.status_code in (415, 422)


@pytest.mark.parametrize(
    "files",
    [
        [("file", ("a.txt", b"a")), ("file", ("b.txt", b"b"))],
        [("document", ("a.txt", b"a"))],
    ],
)
def test_malformed_forms_are_refused(api, user, files) -> None:
    assert api.post(EVIDENCE, files=files, headers=_csrf(api)).status_code == 400


def test_json_body_is_refused(api, user) -> None:
    response = api.post(EVIDENCE, json={"file": "x"}, headers=_csrf(api))
    assert response.status_code == 415


# --- T10 : isolation des organisations -------------------------------------------------


def test_other_organization_gets_404_like_missing_evidence(api, storage, upload_dir, db_session):
    _login(api)
    evidence_id = _upload(api, b"secret").json()["id"]
    assert api.get(f"{EVIDENCE}/{evidence_id}").status_code == 200

    with TestClient(app, base_url="https://testserver") as other:
        _login(other)
        foreign = other.get(f"{EVIDENCE}/{evidence_id}")
        missing = other.get(f"{EVIDENCE}/{uuid.uuid4()}")
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
        assert other.get(EVIDENCE).json() == []


def test_list_returns_own_evidence_newest_first(api, user) -> None:
    first = _upload(api, b"1").json()["id"]
    second = _upload(api, b"2").json()["id"]
    listed = [e["id"] for e in api.get(EVIDENCE).json()]
    assert set(listed) == {first, second}
    assert api.get(EVIDENCE, params={"limit": 1}).json()[0]["id"] in {first, second}
    assert api.get(EVIDENCE, params={"limit": 101}).status_code == 422


# --- Échec après enregistrement -------------------------------------------------------


class _BrokenStorage(LocalStorage):
    def save_stream(self, key, stream):
        raise OSError("disque plein")


def test_storage_failure_marks_evidence_failed(api, tmp_path, upload_dir, db_session) -> None:
    app.dependency_overrides[get_storage] = lambda: _BrokenStorage(tmp_path / "broken")
    try:
        _login(api)
        response = _upload(api, b"contenu")
    finally:
        app.dependency_overrides.pop(get_storage, None)

    assert response.status_code == 500
    evidence_id = re.search(r"[0-9a-f-]{36}", response.json()["detail"]).group()
    status = db_session.execute(
        text("SELECT status FROM evidence WHERE id = :i"), {"i": evidence_id}
    ).scalar_one()
    assert status == "FAILED"
    for model in (EvidenceFile, CustodyEvent):
        assert _count(db_session, model, model.evidence_id == uuid.UUID(evidence_id)) == 0
    assert list(upload_dir.iterdir()) == []
    assert api.get(f"{EVIDENCE}/{evidence_id}").json()["status"] == "FAILED"


# --- Envoi en flux par la route -------------------------------------------------------


def _multipart_stream(boundary: str, size: int, chunk: int = 1024 * 1024) -> Iterator[bytes]:
    yield (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="image-disque.dd"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    block = bytes(range(256)) * (chunk // 256)
    sent = 0
    while sent < size:
        part = block[: min(chunk, size - sent)]
        sent += len(part)
        yield part
    yield f"\r\n--{boundary}--\r\n".encode()


def test_chunked_multipart_upload(api, user) -> None:
    """Corps envoyé par morceaux, sans Content-Length (transfert « chunked »).
    La mémoire bornée est vérifiée dans test_upload.py : le TestClient de Starlette
    relit tout le corps en mémoire avant de l'envoyer, il ne peut pas la mesurer."""
    size = 20 * 1024 * 1024 + 7
    boundary = "veritas-test-boundary"
    expected = hashlib.sha256()
    for piece in list(_multipart_stream(boundary, size))[1:-1]:
        expected.update(piece)

    response = api.post(
        EVIDENCE,
        content=_multipart_stream(boundary, size),
        headers={**_csrf(api), "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["file"]["size"] == size
    assert response.json()["hash"]["digest"] == expected.hexdigest()


# --- Défauts trouvés en revue de code -----------------------------------------------


class _CorruptingStorage(LocalStorage):
    """Stocke des octets différents, de même taille (disque défaillant, par exemple)."""

    def save_stream(self, key, stream):
        data = stream.read()
        return super().save_stream(key, io.BytesIO(bytes(b ^ 0xFF for b in data)))


def test_stored_copy_is_verified_against_digest(api, tmp_path, upload_dir, db_session, caplog):
    app.dependency_overrides[get_storage] = lambda: _CorruptingStorage(tmp_path / "corrupt")
    try:
        _login(api)
        response = _upload(api, b"contenu original")
    finally:
        app.dependency_overrides.pop(get_storage, None)

    assert response.status_code == 500
    evidence_id = re.search(r"[0-9a-f-]{36}", response.json()["detail"]).group()
    assert api.get(f"{EVIDENCE}/{evidence_id}").json()["status"] == "FAILED"
    # La cause et la clé du fichier resté sans référence sont dans le journal du serveur.
    assert evidence_id in caplog.text
    assert "originals/" in caplog.text
    assert "diffère" in caplog.text


def test_truncated_upload_through_the_route(api, user, storage, db_session) -> None:
    boundary = "coupe"
    before = _count(db_session, Evidence)
    response = api.post(
        EVIDENCE,
        content=(
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="a.bin"\r\n\r\n'
            "debut sans fin"
        ).encode(),
        headers={**_csrf(api), "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 400
    assert _count(db_session, Evidence) == before
    assert _stored_files(storage) == []


def test_malformed_multipart_through_the_route(api, user) -> None:
    response = api.post(
        EVIDENCE,
        content=b"n'importe quoi",
        headers={**_csrf(api), "Content-Type": "multipart/form-data; boundary=xyz"},
    )
    assert response.status_code == 400


def test_title_with_nul_is_a_client_error(api, user) -> None:
    assert _upload(api, b"x", title="abc\x00def").status_code == 400


def test_database_is_not_held_during_reception(api, user, db_session, monkeypatch) -> None:
    """Pendant la réception du fichier, aucune transaction ne reste ouverte."""
    from app.api.v1 import evidence as evidence_routes

    real_receive = evidence_routes.receive_upload
    seen = []

    async def spying_receive(*args, **kwargs):
        seen.append(db_session.in_transaction())
        return await real_receive(*args, **kwargs)

    monkeypatch.setattr(evidence_routes, "receive_upload", spying_receive)
    assert _upload(api, b"x").status_code == 201
    assert seen == [False]


def test_failure_while_marking_failed_still_answers_cleanly(
    api, tmp_path, upload_dir, monkeypatch, caplog
) -> None:
    from app.evidence import service as evidence_service

    def broken_mark_failed(*args, **kwargs):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(evidence_service, "_mark_failed", broken_mark_failed)
    app.dependency_overrides[get_storage] = lambda: _BrokenStorage(tmp_path / "broken")
    try:
        _login(api)
        response = _upload(api, b"x")
    finally:
        app.dependency_overrides.pop(get_storage, None)
    assert response.status_code == 500
    assert "FAILED" in response.json()["detail"]
    assert "Impossible de marquer" in caplog.text
