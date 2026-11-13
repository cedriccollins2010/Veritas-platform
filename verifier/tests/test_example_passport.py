"""Le passeport d'exemple publié avec la spécification est valide selon chaque contrôle.

Ces tests refont, avec la bibliothèque, les calculs que SPECIFICATION.md (section 5) décrit
et que examples/passport-v1/README.md fait faire à la main. Ils garantissent que l'exemple
publié et la spécification restent d'accord.
"""

import hashlib
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import jsonschema
import pytest
from cryptography import x509

from veritas_verifier import canonical, custody_chain, passport
from veritas_verifier import manifest as manifest_crypto
from veritas_verifier.hash_service import digests_match
from veritas_verifier.timestamp_verification import Check, CheckStatus, verify_timestamp_token

EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "passport-v1"
ARCHIVE = next(EXAMPLE_DIR.glob("veritas-passport-*.zip"))
ROOT = x509.load_pem_x509_certificate((EXAMPLE_DIR / "example-root-ca.pem").read_bytes())


@pytest.fixture(scope="module")
def contents() -> dict[str, bytes]:
    with zipfile.ZipFile(ARCHIVE) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


@pytest.fixture(scope="module")
def manifest(contents) -> dict:
    return json.loads(contents[passport.MANIFEST_PATH])


def _chain(manifest: dict) -> list[custody_chain.ChainEvent]:
    evidence_id = manifest["evidence"]["id"]
    return [
        custody_chain.ChainEvent(evidence_id=evidence_id, **event)
        for event in manifest["custody"]["events"]
    ]


def test_archive_name_carries_the_evidence_id(manifest) -> None:
    assert ARCHIVE.name == f"veritas-passport-{manifest['evidence']['id']}.zip"


def test_archive_contains_exactly_the_expected_entries(contents, manifest) -> None:
    assert set(contents) == passport.expected_entries(manifest)
    assert all(passport.is_valid_entry_name(name) for name in contents)


def test_repacking_the_entries_gives_the_same_archive(contents) -> None:
    """Déterminisme : n'importe qui peut reconstruire l'archive à l'identique."""
    buffer = io.BytesIO()
    passport.write_passport(buffer, contents)
    assert buffer.getvalue() == ARCHIVE.read_bytes()


# --- MANIFEST --------------------------------------------------------------------------


def test_manifest_is_canonical_and_sealed(contents, manifest) -> None:
    assert contents[passport.MANIFEST_PATH] == canonical.canonicalize(manifest)
    assert manifest_crypto.digest_is_valid(manifest)


def test_manifest_follows_the_published_schema(manifest) -> None:
    jsonschema.Draft202012Validator(manifest_crypto.load_schema("1.1")).validate(manifest)


# --- INTEGRITY -------------------------------------------------------------------------


def test_original_matches_size_and_digest(contents, manifest) -> None:
    for file in manifest["files"]:
        data = contents[passport.original_path(file["id"])]
        assert len(data) == file["size"]
        assert digests_match(file["hashes"][0]["digest"], hashlib.sha256(data).hexdigest())


# --- TIMESTAMP et CERTIFICATE ----------------------------------------------------------


def test_every_token_is_valid_for_its_imprint(contents, manifest) -> None:
    assert {t["purpose"] for t in manifest["timestamps"]} == {"FILE", "CHAIN_HEAD"}
    for item in manifest["timestamps"]:
        token = contents[item["token"]["path"]]
        request = contents[item["request"]["path"]]
        assert hashlib.sha256(token).hexdigest() == item["token"]["sha256"]
        assert hashlib.sha256(request).hexdigest() == item["request"]["sha256"]
        result = verify_timestamp_token(token, request, item["message_imprint"], [ROOT])
        assert result.valid, result.checks
        assert result.status_of(Check.REVOCATION) is CheckStatus.UNKNOWN
        # Ce que dit le manifeste doit être ce que dit le jeton.
        generation_time = custody_chain.format_timestamp(result.generation_time)
        assert generation_time == item["generation_time"]
        assert result.serial_number == item["serial_number"]
        assert result.policy_oid == item["policy_oid"] == "2.999.1"


def test_file_token_covers_the_file_digest(manifest) -> None:
    file_token = next(t for t in manifest["timestamps"] if t["purpose"] == "FILE")
    assert file_token["message_imprint"] == manifest["files"][0]["hashes"][0]["digest"]


def test_example_root_is_not_trusted_by_default(contents, manifest) -> None:
    """La racine d'exemple doit être ajoutée explicitement : sans elle, la chaîne échoue."""
    item = manifest["timestamps"][0]
    token, request = contents[item["token"]["path"]], contents[item["request"]["path"]]
    result = verify_timestamp_token(token, request, item["message_imprint"], [])
    assert result.status_of(Check.SIGNATURE_AND_CHAIN) is CheckStatus.FAIL
    assert not result.valid


# --- CUSTODY ---------------------------------------------------------------------------


def test_custody_chain_and_anchor_are_valid(manifest) -> None:
    events = _chain(manifest)
    assert custody_chain.verify_chain(events).passed
    custody = manifest["custody"]
    assert custody["event_count"] == len(events)
    assert custody["head_hash"] == events[-1].event_hash
    anchor = next(t for t in manifest["timestamps"] if t["purpose"] == "CHAIN_HEAD")
    status = manifest["timestamp_status"]
    assert status["anchored_sequence_number"] == anchor["anchored_sequence_number"] == 2
    assert status["unanchored_events"] == len(events) - 2
    result = custody_chain.verify_anchor(
        events, anchor["anchored_sequence_number"], anchor["message_imprint"]
    )
    assert result.passed


# --- Vérification à la main ------------------------------------------------------------


@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL absent")
def test_openssl_agrees(contents, manifest, tmp_path: Path) -> None:
    """La commande du README (openssl ts -verify) confirme chaque jeton."""
    root = EXAMPLE_DIR / "example-root-ca.pem"
    for item in manifest["timestamps"]:
        (tmp_path / "token.tsr").write_bytes(contents[item["token"]["path"]])
        (tmp_path / "request.tsq").write_bytes(contents[item["request"]["path"]])
        result = subprocess.run(  # noqa: S603 — openssl, arguments écrits ci-dessus
            [
                shutil.which("openssl"),
                "ts",
                "-verify",
                "-queryfile",
                str(tmp_path / "request.tsq"),
                "-in",
                str(tmp_path / "token.tsr"),
                "-CAfile",
                str(root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert "Verification: OK" in result.stdout, result.stderr


# --- MANIFEST : concordance avec la chaîne (SPECIFICATION.md, 5.1, points 6 à 8) -------


def test_files_agree_with_their_deposit_event(manifest) -> None:
    events = manifest["custody"]["events"]
    for file in manifest["files"]:
        deposit_type = "FILE_RECEIVED" if file["storage_mode"] == "STORED" else "HASH_DECLARED"
        matching = [
            e
            for e in events
            if e["event_type"] == deposit_type and e["event_data"].get("file_id") == file["id"]
        ]
        assert len(matching) == 1
        data = matching[0]["event_data"]
        digest = file["hashes"][0]
        assert data["original_filename"] == file["original_filename"]
        assert data["media_type"] == file["media_type"]
        assert data["size"] == file["size"]
        assert data["storage_mode"] == file["storage_mode"]
        assert data["hash_algorithm"] == "SHA-256"
        assert data["digest"] == digest["digest"]
        assert data["hash_source"] == digest["source"]


def test_tokens_agree_with_their_custody_event(manifest) -> None:
    by_record = {
        e["event_data"].get("timestamp_record_id"): e for e in manifest["custody"]["events"]
    }
    for item in manifest["timestamps"]:
        event = by_record[item["timestamp_record_id"]]
        data = event["event_data"]
        assert data["token_sha256"] == item["token"]["sha256"]
        assert data["generation_time"] == item["generation_time"]
        assert data["serial_number"] == item["serial_number"]
        if item["purpose"] == "FILE":
            assert event["event_type"] == "TIMESTAMP_ATTACHED"
            assert data["purpose"] == "FILE"
            assert data["message_imprint"] == item["message_imprint"]
            assert data["policy_oid"] == item["policy_oid"]
        else:
            assert event["event_type"] == "CHAIN_ANCHORED"
            assert data["anchored_sequence_number"] == item["anchored_sequence_number"]
            assert data["anchored_hash"] == item["message_imprint"]


def test_timestamp_status_is_consistent(manifest) -> None:
    status = manifest["timestamp_status"]
    purposes = [t["purpose"] for t in manifest["timestamps"]]
    anchored = [
        t["anchored_sequence_number"]
        for t in manifest["timestamps"]
        if t["purpose"] == "CHAIN_HEAD"
    ]
    assert (status["file"] == "VALID") == ("FILE" in purposes)
    assert (status["chain_head"] == "ANCHORED") == bool(anchored)
    assert status["anchored_sequence_number"] == max(anchored, default=None)
    expected = manifest["custody"]["event_count"] - (status["anchored_sequence_number"] or 0)
    assert status["unanchored_events"] == expected


def test_readme_quotes_the_values_of_this_archive(manifest) -> None:
    """Après une régénération de l'exemple, le README doit être mis à jour."""
    readme = (EXAMPLE_DIR / "README.md").read_text(encoding="utf-8")
    assert ARCHIVE.name in readme
    assert manifest["files"][0]["hashes"][0]["digest"] in readme
    assert manifest["custody"]["events"][1]["event_hash"] in readme
    for item in manifest["timestamps"]:
        assert item["token"]["path"] in readme
        assert item["request"]["path"].removesuffix(".tsq") in readme
