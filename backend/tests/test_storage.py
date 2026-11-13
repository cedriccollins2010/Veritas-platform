"""Suite commune aux implémentations de Storage (issue #4).

Chaque test s'exécute sur LocalStorage (dossier temporaire) et sur S3Storage (faux
service S3 en mémoire fourni par moto). Une nouvelle implémentation s'ajoute à la
fixture `storage` et doit passer exactement les mêmes tests.
"""

import io
import os
import stat
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from app.core.config import Settings
from app.crypto.hash_service import sha256_stream
from app.storage import (
    InvalidStorageKeyError,
    Storage,
    StorageKeyExistsError,
    StorageKeyNotFoundError,
    new_storage_key,
)
from app.storage.factory import create_storage
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage

BUCKET = "veritas-test"


@pytest.fixture
def s3_client(monkeypatch) -> Iterator[object]:
    # Identifiants factices : moto n'appelle aucun service réel.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


@pytest.fixture(params=["local", "s3"])
def storage(request, tmp_path: Path) -> Storage:
    if request.param == "local":
        return LocalStorage(tmp_path / "storage")
    return S3Storage(request.getfixturevalue("s3_client"), BUCKET)


def _read(storage: Storage, key: str) -> bytes:
    with storage.open(key) as stream:
        return stream.read()


# --- Suite commune ------------------------------------------------------------------


def test_round_trip(storage: Storage) -> None:
    key = new_storage_key()
    assert not storage.exists(key)
    assert storage.save_stream(key, io.BytesIO(b"contenu de test")) == 15
    assert storage.exists(key)
    assert storage.size(key) == 15
    assert _read(storage, key) == b"contenu de test"


def test_large_stream_is_stored_exactly(storage: Storage) -> None:
    """Plusieurs blocs de 1 Mo, et une taille qui n'est pas un multiple du bloc."""
    data = os.urandom(3 * 1024 * 1024 + 123)
    key = new_storage_key()
    assert storage.save_stream(key, io.BytesIO(data)) == len(data)
    with storage.open(key) as stream:
        assert sha256_stream(stream) == sha256_stream(io.BytesIO(data))


def test_empty_file(storage: Storage) -> None:
    key = new_storage_key()
    assert storage.save_stream(key, io.BytesIO(b"")) == 0
    assert storage.size(key) == 0


def test_save_twice_is_refused_and_original_kept(storage: Storage) -> None:
    key = new_storage_key()
    storage.save_stream(key, io.BytesIO(b"original"))
    with pytest.raises(StorageKeyExistsError):
        storage.save_stream(key, io.BytesIO(b"remplacement"))
    assert _read(storage, key) == b"original"


def test_missing_key(storage: Storage) -> None:
    key = new_storage_key()
    assert not storage.exists(key)
    with pytest.raises(StorageKeyNotFoundError):
        storage.size(key)
    with pytest.raises(StorageKeyNotFoundError):
        storage.open(key)


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "originals/../../etc/passwd",
        "/etc/passwd",
        "originals/..",
        "..",
        "",
        ".incoming/fichier",
        "originals//double",
        "originals/",
        "originals\\windows",
        "Originals/Majuscules",
        "originals/nul\x00",
        "originals/" + "a" * 600,
    ],
)
def test_dangerous_keys_are_refused(storage: Storage, key: str) -> None:
    with pytest.raises(InvalidStorageKeyError):
        storage.save_stream(key, io.BytesIO(b"x"))
    with pytest.raises(InvalidStorageKeyError):
        storage.exists(key)
    with pytest.raises(InvalidStorageKeyError):
        storage.open(key)


def test_generated_keys_are_unique_and_valid() -> None:
    keys = {new_storage_key() for _ in range(1000)}
    assert len(keys) == 1000
    assert all(key.startswith("originals/") for key in keys)


# --- Propres au disque local ----------------------------------------------------------


def test_local_traversal_writes_nothing_outside_root(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    before = set(tmp_path.rglob("*"))
    with pytest.raises(InvalidStorageKeyError):
        storage.save_stream("../evil", io.BytesIO(b"x"))
    assert set(tmp_path.rglob("*")) == before
    assert not (tmp_path / "evil").exists()


@pytest.mark.skipif(os.name != "posix", reason="droits POSIX")
def test_local_files_are_read_only(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    key = new_storage_key()
    storage.save_stream(key, io.BytesIO(b"x"))
    mode = stat.S_IMODE((tmp_path / "storage" / key).stat().st_mode)
    assert mode == 0o440


class _BrokenStream(io.RawIOBase):
    """Flux qui échoue après un premier bloc, comme une connexion coupée."""

    def __init__(self) -> None:
        self.calls = 0

    def read(self, size: int = -1) -> bytes:
        self.calls += 1
        if self.calls > 1:
            raise ConnectionResetError("téléversement interrompu")
        return b"debut"


def test_local_interrupted_write_leaves_nothing(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    key = new_storage_key()
    with pytest.raises(ConnectionResetError):
        storage.save_stream(key, _BrokenStream())
    assert not storage.exists(key)
    assert list((tmp_path / "storage" / ".incoming").iterdir()) == []


def test_local_concurrent_writers_cannot_both_succeed(tmp_path: Path) -> None:
    """La publication par lien physique échoue si la clé est apparue entre-temps."""
    storage = LocalStorage(tmp_path / "storage")
    key = new_storage_key()

    class RacingStream(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            data = super().read(size)
            if not data and not storage.exists(key):
                # Un autre écrivain publie la même clé pendant notre écriture.
                LocalStorage(tmp_path / "storage").save_stream(key, io.BytesIO(b"premier"))
            return data

    with pytest.raises(StorageKeyExistsError):
        storage.save_stream(key, RacingStream(b"second"))
    assert _read(storage, key) == b"premier"


# --- Choix de l'implémentation -------------------------------------------------------


def test_factory_selects_local_by_default(tmp_path: Path) -> None:
    storage = create_storage(Settings(local_storage_path=tmp_path / "s"))
    assert isinstance(storage, LocalStorage)


def test_factory_selects_s3(s3_client) -> None:
    storage = create_storage(Settings(storage_backend="s3", s3_bucket=BUCKET))
    assert isinstance(storage, S3Storage)
    key = new_storage_key()
    storage.save_stream(key, io.BytesIO(b"via la configuration"))
    assert storage.size(key) == 20


def test_factory_requires_bucket_for_s3() -> None:
    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        create_storage(Settings(storage_backend="s3"))
