"""Format veritas-passport-v1 : noms d'entrée, contenu exact et écriture déterministe (#34)."""

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest

from veritas_verifier import manifest as manifest_crypto
from veritas_verifier import passport
from veritas_verifier.passport import PassportFormatError

FILE_ID = "c4e8a1f2-7b3d-4e5f-9a6b-0c1d2e3f4a50"
TS_ID = "e1f2a3b4-c5d6-4e7f-8091-a2b3c4d5e6f7"


def _manifest(storage_mode: str = "STORED", with_timestamp: bool = True) -> dict:
    """Manifeste minimal : seuls les champs lus par le format d'archive."""
    timestamps = []
    if with_timestamp:
        token, request = passport.timestamp_paths(TS_ID)
        timestamps.append(
            {
                "timestamp_record_id": TS_ID,
                "token": {"path": token, "sha256": "a" * 64},
                "request": {"path": request, "sha256": "b" * 64},
            }
        )
    return manifest_crypto.seal(
        {
            "format": "veritas-manifest",
            "format_version": "1.1",
            "files": [{"id": FILE_ID, "storage_mode": storage_mode}],
            "timestamps": timestamps,
        }
    )


def _entries(document: dict | None = None) -> dict[str, bytes]:
    document = document or _manifest()
    entries = {name: name.encode() for name in passport.expected_entries(document)}
    entries[passport.MANIFEST_PATH] = manifest_crypto.to_bytes(document)
    return entries


def _write(entries) -> bytes:
    buffer = io.BytesIO()
    passport.write_passport(buffer, entries)
    return buffer.getvalue()


# --- Noms d'entrée --------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "manifest.json",
        f"original/{FILE_ID}",
        f"timestamp/{TS_ID}.tsr",
        f"timestamp/{TS_ID}.tsq",
    ],
)
def test_valid_entry_names(name: str) -> None:
    assert passport.is_valid_entry_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "../manifest.json",
        "/manifest.json",
        "./manifest.json",
        "manifest.json/",
        "Manifest.json",
        "original/note-incident.txt",  # jamais le nom d'origine
        f"original/../{FILE_ID}",
        f"original\\{FILE_ID}",
        f"original/{FILE_ID.upper()}",
        f"original/{FILE_ID}/",
        f"original//{FILE_ID}",
        f"timestamp/{TS_ID}.tsr.exe",
        f"timestamp/{TS_ID}.TSR",
        f"timestamp/{TS_ID}",
        f"report/{FILE_ID}",
        "custody/custody-events.json",
        f"original/{FILE_ID}\x00",
        f"original/{FILE_ID}\n",
        "manifest.json​",
        "",
    ],
)
def test_invalid_entry_names(name: str) -> None:
    assert not passport.is_valid_entry_name(name)


def test_original_filename_is_never_a_path() -> None:
    with pytest.raises(PassportFormatError):
        passport.original_path("../../etc/passwd")


# --- Ensemble exact des entrées ------------------------------------------------------


def test_expected_entries_of_a_stored_file() -> None:
    token, request = passport.timestamp_paths(TS_ID)
    assert passport.expected_entries(_manifest()) == {
        "manifest.json",
        f"original/{FILE_ID}",
        token,
        request,
    }


def test_hash_only_file_has_no_original() -> None:
    entries = passport.expected_entries(_manifest("HASH_ONLY", with_timestamp=False))
    assert entries == {"manifest.json"}


def test_non_canonical_timestamp_path_is_refused() -> None:
    document = _manifest()
    document["timestamps"][0]["token"]["path"] = f"timestamp/{FILE_ID}.tsr"
    with pytest.raises(PassportFormatError, match="non canonique"):
        passport.expected_entries(document)


@pytest.mark.parametrize("version", ["1.0", "1.2", "2.0", 1.1])
def test_other_manifest_versions_are_refused(version) -> None:
    document = copy.deepcopy(_manifest())
    document["format_version"] = version
    with pytest.raises(PassportFormatError):
        passport.expected_entries(document)


def test_incomplete_manifest_is_a_format_error() -> None:
    document = _manifest()
    del document["files"]
    with pytest.raises(PassportFormatError):
        passport.expected_entries(document)


# --- Écriture -------------------------------------------------------------------------


def test_archive_attributes_are_fixed() -> None:
    with zipfile.ZipFile(io.BytesIO(_write(_entries()))) as archive:
        infos = archive.infolist()
        assert archive.comment == b""
    assert [info.filename for info in infos] == sorted(info.filename for info in infos)
    assert infos[0].filename == "manifest.json"
    for info in infos:
        assert info.compress_type == zipfile.ZIP_STORED
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert info.create_system == 3
        assert info.external_attr == 0o100644 << 16
        assert info.flag_bits == 0  # ni chiffrement, ni « data descriptor », ni UTF-8
        assert info.extra == b""
        assert info.comment == b""
        assert not info.is_dir()


def test_two_writes_are_identical_byte_for_byte() -> None:
    entries = _entries()
    reversed_entries = dict(reversed(list(entries.items())))
    assert _write(entries) == _write(reversed_entries)


def test_file_on_disk_gives_the_same_archive_as_bytes(tmp_path: Path) -> None:
    entries = _entries()
    original = f"original/{FILE_ID}"
    on_disk = tmp_path / "piece"
    on_disk.write_bytes(entries[original])
    assert _write({**entries, original: on_disk}) == _write(entries)


def test_content_is_kept_exactly() -> None:
    entries = _entries()
    with zipfile.ZipFile(io.BytesIO(_write(entries))) as archive:
        for name, content in entries.items():
            assert archive.read(name) == content


def test_missing_entry_is_refused() -> None:
    entries = _entries()
    del entries[f"original/{FILE_ID}"]
    with pytest.raises(PassportFormatError, match="manquantes"):
        _write(entries)


def test_extra_entry_is_refused() -> None:
    entries = _entries()
    entries[f"original/{TS_ID}"] = b"intrus"
    with pytest.raises(PassportFormatError, match="en trop"):
        _write(entries)


def test_invalid_name_is_refused() -> None:
    entries = _entries()
    entries["report/report.pdf"] = b"%PDF"
    with pytest.raises(PassportFormatError, match="non conformes"):
        _write(entries)


def test_non_canonical_manifest_is_refused() -> None:
    entries = _entries()
    pretty = json.dumps(json.loads(entries["manifest.json"]), indent=2).encode()
    with pytest.raises(PassportFormatError, match="canonique"):
        _write({**entries, "manifest.json": pretty})


def test_unreadable_manifest_is_refused() -> None:
    with pytest.raises(PassportFormatError, match="illisible"):
        _write({**_entries(), "manifest.json": b"{not json"})


def test_manifest_must_be_bytes(tmp_path: Path) -> None:
    entries = _entries()
    path = tmp_path / "manifest.json"
    path.write_bytes(entries["manifest.json"])
    with pytest.raises(PassportFormatError, match="octets"):
        _write({**entries, "manifest.json": path})


def test_destination_must_be_seekable() -> None:
    class Unseekable(io.BytesIO):
        def seekable(self) -> bool:
            return False

    with pytest.raises(PassportFormatError, match="accès direct"):
        passport.write_passport(Unseekable(), _entries())
