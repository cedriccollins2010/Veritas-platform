"""Tests de la vérification complète d'un jeton RFC 3161 (issue #24, T05)."""

import hashlib

import pytest
from cryptography.hazmat.primitives import hashes
from rfc3161_client import decode_timestamp_response

from app.crypto.timestamp_verification import (
    MANDATORY,
    Check,
    CheckStatus,
    verify_timestamp_token,
)
from app.timestamp.request import build_request
from app.timestamp.roots import load_trust_roots
from tests.local_tsa import run_openssl

DIGEST = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
OTHER_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture(scope="module")
def stamped(tsa):
    request = build_request(DIGEST, nonce=424242)
    return request, tsa.reply(request)


def _verify(tsa, response, request, digest=DIGEST):
    return verify_timestamp_token(response, request, digest, [tsa.root()])


def _failed(result) -> set[Check]:
    return {r.check for r in result.checks if r.status is CheckStatus.FAIL}


# --- Jeton valide ---------------------------------------------------------------------


def test_valid_token(tsa, stamped) -> None:
    request, response = stamped
    result = _verify(tsa, response, request)

    assert result.valid
    assert _failed(result) == set()
    assert {r.check for r in result.checks} == set(Check)
    assert result.status_of(Check.REVOCATION) is CheckStatus.UNKNOWN  # jamais de PASS artificiel
    assert result.policy_oid == "1.2.3.4.1"
    assert result.tsa_subject == "CN=VERITAS Test TSA"
    assert result.generation_time is not None and result.generation_time.tzinfo is not None
    assert result.serial_number


def test_revocation_unknown_does_not_block_validity(tsa, stamped) -> None:
    assert Check.REVOCATION not in MANDATORY
    assert _verify(tsa, *reversed(stamped)).valid


# --- T05 : jetons falsifiés ou inadaptés ------------------------------------------------


def test_token_for_another_digest(tsa) -> None:
    request = build_request(OTHER_DIGEST, nonce=1)
    result = _verify(tsa, tsa.reply(request), request, DIGEST)
    assert not result.valid
    assert {Check.MESSAGE_IMPRINT, Check.REQUEST_MATCH} <= _failed(result)


def test_token_with_another_nonce(tsa, stamped) -> None:
    _, response = stamped
    other_request = build_request(DIGEST, nonce=999)
    result = _verify(tsa, response, other_request)
    assert not result.valid
    assert _failed(result) == {Check.NONCE}


def test_token_from_an_untrusted_tsa(tsa, rogue_tsa) -> None:
    request = build_request(DIGEST, nonce=7)
    forged = rogue_tsa.reply(request)
    result = _verify(tsa, forged, request)  # seule la racine de la TSA légitime est connue
    assert not result.valid
    assert _failed(result) == {Check.SIGNATURE_AND_CHAIN}


def test_no_trust_root_means_invalid(tsa, stamped) -> None:
    request, response = stamped
    result = verify_timestamp_token(response, request, DIGEST, [])
    assert not result.valid
    assert _failed(result) == {Check.SIGNATURE_AND_CHAIN}


def test_rejection_response(tsa, tmp_path) -> None:
    sha1_query = run_openssl(
        "ts",
        "-query",
        "-digest",
        "a9993e364706816aba3e25717850c26c9cd0d89d",
        "-sha1",
        "-no_nonce",
        cwd=tmp_path,
    )
    result = _verify(tsa, tsa.reply(sha1_query), build_request(DIGEST, nonce=1))
    assert not result.valid
    assert Check.STATUS_GRANTED in _failed(result)


@pytest.mark.parametrize("garbage", [b"", b"\x30\x00", b"pas un jeton", bytes(200)])
def test_unreadable_response_never_crashes(tsa, garbage) -> None:
    result = _verify(tsa, garbage, build_request(DIGEST, nonce=1))
    assert not result.valid
    assert result.status_of(Check.RESPONSE_READABLE) is CheckStatus.FAIL
    assert all(result.status_of(check) is CheckStatus.FAIL for check in MANDATORY)


def _attested(response: bytes):
    """Ce que la TSA atteste (couvert par sa signature) : date, empreinte, nonce, série."""
    info = decode_timestamp_response(response).tst_info
    return (info.gen_time, info.message_imprint.message, info.nonce, info.serial_number)


def test_a_byte_change_never_alters_what_is_attested(tsa, stamped) -> None:
    """Un octet modifié, à chacune des positions du jeton : soit le jeton devient
    invalide, soit ce qu'il atteste reste rigoureusement identique.

    Quelques octets de l'enveloppe CMS ne sont pas couverts par la signature : les
    numéros de version de SignedData et de SignerInfo, et l'étiquette de l'algorithme
    de signature (la signature est vérifiée avec la clé de la TSA, quelle que soit
    l'étiquette). OpenSSL les accepte de la même façon. Les modifier ne change ni la
    date, ni l'empreinte, ni le nonce attestés : ce n'est pas une falsification.
    C'est pourquoi l'empreinte du fichier .tsr conservé sera aussi enregistrée dans la
    chaîne de possession (issue #25) : toute modification du fichier restera visible.
    """
    request, response = stamped
    original = _attested(response)
    still_valid = []
    for position in range(len(response)):
        altered = bytearray(response)
        altered[position] ^= 0x01
        if _verify(tsa, bytes(altered), request).valid:
            assert _attested(bytes(altered)) == original, f"octet {position}"
            still_valid.append(position)
    # Ces octets malléables sont rares (une dizaine sur environ mille).
    assert len(still_valid) < len(response) // 20, still_valid


# --- Comparaison avec openssl ts -verify ------------------------------------------------


def _corpus(tsa, rogue_tsa, request, response):
    yield "valide", response, request
    yield "autre empreinte", tsa.reply(build_request(OTHER_DIGEST, nonce=424242)), request
    yield "autre nonce", tsa.reply(build_request(DIGEST, nonce=5)), request
    yield "autre TSA", rogue_tsa.reply(request), request
    step = max(1, len(response) // 40)
    for position in range(0, len(response), step):
        altered = bytearray(response)
        altered[position] ^= 0x01
        yield f"octet {position}", bytes(altered), request


def test_verdicts_match_openssl(tsa, rogue_tsa, stamped) -> None:
    """Pour chaque jeton du corpus, notre verdict est celui d'openssl ts -verify."""
    request, response = stamped
    disagreements = []
    for label, token, query in _corpus(tsa, rogue_tsa, request, response):
        ours = _verify(tsa, token, query).valid
        theirs = tsa.openssl_verdict(token, query)
        if ours != theirs:
            disagreements.append((label, ours, theirs))
    assert disagreements == []


# --- Racines de confiance versionnées ----------------------------------------------------


def test_digicert_root_is_pinned() -> None:
    roots = {
        root.subject.rfc4514_string(): root.fingerprint(hashes.SHA256()).hex()
        for root in load_trust_roots()
    }
    assert roots["CN=DigiCert Trusted Root G4,OU=www.digicert.com,O=DigiCert Inc,C=US"] == (
        "552f7bdcf1a7af9e6ce672017f4f12abf77240c78e761ac203d1d9d20ac89988"
    )


def test_test_tsa_is_not_trusted_in_production(tsa, stamped) -> None:
    """Un jeton de la TSA de test n'est pas valide avec les racines de production."""
    request, response = stamped
    assert not verify_timestamp_token(response, request, DIGEST, load_trust_roots()).valid


def test_digest_argument_is_normalized(tsa, stamped) -> None:
    request, response = stamped
    assert _verify(tsa, response, request, DIGEST.upper()).valid
    assert hashlib.sha256(b"abc").hexdigest() == DIGEST


# --- Enregistrement dans timestamp_records ---------------------------------------------


def _hash_record(db_session):
    """Une preuve avec son empreinte, créée directement par l'ORM."""
    import uuid as _uuid

    from app.auth.models import User
    from app.evidence.models import Evidence, EvidenceFile, HashRecord
    from app.organizations.models import Organization

    user = User(email=f"tsa-{_uuid.uuid4().hex[:8]}@exemple.test", password_hash="x")
    organization = Organization(name="Test", is_personal=True)
    db_session.add_all([user, organization])
    db_session.flush()
    evidence = Evidence(organization_id=organization.id, owner_id=user.id, title="T")
    db_session.add(evidence)
    db_session.flush()
    file = EvidenceFile(
        evidence_id=evidence.id,
        original_filename="a",
        storage_mode="HASH_ONLY",
        file_size=1,
    )
    db_session.add(file)
    db_session.flush()
    record = HashRecord(
        file_id=file.id, algorithm="SHA-256", digest=DIGEST, engine_version="1.0", source="CLIENT"
    )
    db_session.add(record)
    db_session.flush()
    return evidence, record


def _timestamp_record(db_session, evidence, hash_record, token_key):
    from app.timestamp.models import TimestampRecord

    record = TimestampRecord(
        evidence_id=evidence.id,
        purpose="FILE",
        hash_record_id=hash_record.id,
        hash_algorithm="SHA-256",
        message_imprint=DIGEST,
        tsa_name="TSA de test",
        tsa_url="https://tsa.test/tsr",
        nonce=424242,
        token_storage_key=token_key,
    )
    db_session.add(record)
    return record


@pytest.mark.integration
def test_valid_result_is_recorded(db_session, tsa, stamped) -> None:
    from app.timestamp.service import apply_verification

    request, response = stamped
    evidence, hash_record = _hash_record(db_session)
    record = _timestamp_record(db_session, evidence, hash_record, "timestamps/x.tsr")
    apply_verification(record, _verify(tsa, response, request))
    db_session.flush()

    assert record.validation_status == "VALID"
    assert record.policy_oid == "1.2.3.4.1"
    assert record.generation_time is not None and record.serial_number
    assert record.error_detail is None and record.validated_at is not None


@pytest.mark.integration
def test_invalid_result_lists_the_failed_checks(db_session, tsa, rogue_tsa) -> None:
    from app.timestamp.service import apply_verification

    request = build_request(DIGEST, nonce=424242)
    evidence, hash_record = _hash_record(db_session)
    record = _timestamp_record(db_session, evidence, hash_record, "timestamps/y.tsr")
    apply_verification(record, _verify(tsa, rogue_tsa.reply(request), request))
    db_session.flush()

    assert record.validation_status == "INVALID"
    assert "SIGNATURE_AND_CHAIN" in record.error_detail


@pytest.mark.integration
def test_database_refuses_valid_without_stored_token(db_session, tsa, stamped) -> None:
    """Contrainte de la migration 0001 : VALID exige un jeton conservé et sa date."""
    from sqlalchemy.exc import IntegrityError

    from app.timestamp.service import apply_verification

    request, response = stamped
    evidence, hash_record = _hash_record(db_session)
    savepoint = db_session.begin_nested()
    record = _timestamp_record(db_session, evidence, hash_record, token_key=None)
    apply_verification(record, _verify(tsa, response, request))
    with pytest.raises(IntegrityError, match="timestamp_records_check1"):
        db_session.flush()
    savepoint.rollback()
