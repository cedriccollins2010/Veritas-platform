"""Tests de la réception en flux (app/evidence/upload.py), sans base de données.

La requête est simulée au niveau ASGI, morceau par morceau, comme la transmet un vrai
serveur (uvicorn) : c'est la seule façon de mesurer la mémoire de notre code.
"""

import asyncio
import hashlib
import tracemalloc
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.requests import Request

from app.evidence.upload import (
    InvalidUploadError,
    UploadTooLargeError,
    clean_filename,
    clean_media_type,
    receive_upload,
)

BOUNDARY = "veritas-boundary"
BLOCK = bytes(range(256)) * 4096  # 1 Mo


def _body(size: int, filename: str = "image.dd", title: str | None = None) -> Iterator[bytes]:
    if title is not None:
        yield (
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="title"\r\n\r\n{title}\r\n'
        ).encode()
    yield (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/x-raw-disk-image\r\n\r\n"
    ).encode()
    sent = 0
    while sent < size:
        part = BLOCK[: min(len(BLOCK), size - sent)]
        sent += len(part)
        yield part
    yield f"\r\n--{BOUNDARY}--\r\n".encode()


def _request(chunks: Iterator[bytes], content_length: int | None = None) -> Request:
    headers = [(b"content-type", f"multipart/form-data; boundary={BOUNDARY}".encode())]
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))

    async def receive() -> dict:
        chunk = next(chunks, None)
        if chunk is None:
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.request", "body": chunk, "more_body": True}

    return Request({"type": "http", "method": "POST", "headers": headers}, receive)


def _expected_digest(size: int) -> str:
    digest = hashlib.sha256()
    sent = 0
    while sent < size:
        part = BLOCK[: min(len(BLOCK), size - sent)]
        sent += len(part)
        digest.update(part)
    return digest.hexdigest()


def test_large_upload_uses_bounded_memory(tmp_path: Path) -> None:
    """300 Mo reçus par morceaux de 1 Mo : le pic de mémoire Python reste de quelques Mo."""
    size = 300 * 1024 * 1024 + 11
    tracemalloc.start()
    try:
        upload = asyncio.run(
            receive_upload(_request(_body(size)), max_file_bytes=size, temp_dir=tmp_path)
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert upload.size == size
    assert upload.path.stat().st_size == size
    assert upload.sha256 == _expected_digest(size)
    print(f"pic mémoire Python : {peak / 1e6:.1f} Mo pour {size / 1e6:.0f} Mo reçus")
    assert peak < 16 * 1024 * 1024, f"pic mémoire {peak / 1e6:.1f} Mo"
    upload.discard()
    assert list(tmp_path.iterdir()) == []


def test_reception_stops_as_soon_as_limit_is_exceeded(tmp_path: Path) -> None:
    consumed = []

    def counting(chunks: Iterator[bytes]) -> Iterator[bytes]:
        for chunk in chunks:
            consumed.append(len(chunk))
            yield chunk

    limit = 3 * 1024 * 1024
    with pytest.raises(UploadTooLargeError):
        asyncio.run(
            receive_upload(
                _request(counting(_body(100 * 1024 * 1024))),
                max_file_bytes=limit,
                temp_dir=tmp_path,
            )
        )
    # Arrêt après ~4 Mo lus sur 100 Mo envoyés : le reste n'est jamais reçu.
    assert sum(consumed) < limit + 2 * len(BLOCK)
    assert list(tmp_path.iterdir()) == []


def test_declared_size_too_large_is_refused_before_reading(tmp_path: Path) -> None:
    consumed = []

    def counting(chunks: Iterator[bytes]) -> Iterator[bytes]:
        for chunk in chunks:
            consumed.append(chunk)
            yield chunk

    with pytest.raises(UploadTooLargeError):
        asyncio.run(
            receive_upload(
                _request(counting(_body(10)), content_length=10**12),
                max_file_bytes=1024,
                temp_dir=tmp_path,
            )
        )
    assert consumed == []


def test_title_and_metadata(tmp_path: Path) -> None:
    upload = asyncio.run(
        receive_upload(
            _request(_body(5, filename="C:\\Cas 42\\disque.dd", title="  Disque du poste 42 ")),
            max_file_bytes=1024,
            temp_dir=tmp_path,
        )
    )
    assert upload.title == "Disque du poste 42"
    assert upload.original_filename == "disque.dd"
    assert upload.media_type == "application/x-raw-disk-image"
    upload.discard()


def test_not_multipart_is_refused(tmp_path: Path) -> None:
    request = Request(
        {"type": "http", "method": "POST", "headers": [(b"content-type", b"application/json")]},
        lambda: None,
    )
    with pytest.raises(InvalidUploadError) as error:
        asyncio.run(receive_upload(request, max_file_bytes=1024, temp_dir=tmp_path))
    assert error.value.status_code == 415


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"rapport.pdf", "rapport.pdf"),
        (b"../../etc/passwd", "passwd"),
        (b"C:\\Users\\x\\note.txt", "note.txt"),
        (b"nom\x00\x1bcache.txt", "nomcache.txt"),
        (b"", "fichier"),
        (b"..", "fichier"),
        (b"dossier/.", "fichier"),
        ("é".encode() * 300, "é" * 255),
    ],
)
def test_clean_filename(raw: bytes, expected: str) -> None:
    assert clean_filename(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("text/plain; charset=utf-8", "text/plain"),
        ("Application/PDF", "application/pdf"),
        ("pas un type", "application/octet-stream"),
        ("text/html\r\nX-Injection: 1", "application/octet-stream"),
        (None, "application/octet-stream"),
    ],
)
def test_clean_media_type(raw: str | None, expected: str) -> None:
    assert clean_media_type(raw) == expected


# --- Défauts trouvés en revue de code -----------------------------------------------


def _raw_request(chunks: list[bytes]) -> Request:
    return _request(iter(chunks))


def test_truncated_body_is_refused(tmp_path: Path) -> None:
    """Un corps coupé avant la frontière finale n'est PAS un fichier complet : sinon on
    enregistrerait comme preuve l'empreinte d'un fichier partiel."""
    head = (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="a.bin"\r\n\r\n'
    ).encode()
    with pytest.raises(InvalidUploadError):
        asyncio.run(
            receive_upload(
                _raw_request([head, b"DEBUT DU FICHIER SANS FIN"]),
                max_file_bytes=1024,
                temp_dir=tmp_path,
            )
        )
    assert list(tmp_path.iterdir()) == []


def test_malformed_multipart_is_a_client_error(tmp_path: Path) -> None:
    with pytest.raises(InvalidUploadError) as error:
        asyncio.run(
            receive_upload(
                _raw_request([b"ceci ne commence pas par la frontiere\r\n"]),
                max_file_bytes=1024,
                temp_dir=tmp_path,
            )
        )
    assert error.value.status_code == 400
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("title", ["abc\x00def", "ligne\nnouvelle", "tab\tulation"])
def test_title_with_control_characters_is_refused(tmp_path: Path, title: str) -> None:
    with pytest.raises(InvalidUploadError):
        asyncio.run(
            receive_upload(_request(_body(3, title=title)), max_file_bytes=1024, temp_dir=tmp_path)
        )
