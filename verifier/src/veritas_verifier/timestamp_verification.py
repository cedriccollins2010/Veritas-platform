"""Vérification complète d'un jeton d'horodatage RFC 3161 (issue #24).

Fonction pure : ni base de données, ni réseau, ni horloge système. Elle reçoit la
réponse et la requête conservées, l'empreinte attendue et les racines de confiance, et
rend un résultat par contrôle. Le serveur et le vérificateur autonome l'appellent
tous deux.

Contrôles obligatoires (le jeton n'est VALID que si tous sont PASS) :
- RESPONSE_READABLE : la réponse se décode (rfc3161-client, analyse DER stricte) ;
- STATUS_GRANTED : la TSA a accordé l'horodatage ;
- MESSAGE_IMPRINT : l'empreinte horodatée est SHA-256 et égale à l'empreinte attendue ;
- REQUEST_MATCH : la requête conservée portait bien cette empreinte ;
- NONCE : le nonce du jeton est celui de la requête ;
- TSA_CERTIFICATE : le certificat qui a signé est désigné par la signature et porte
  l'usage critique id-kp-timeStamping (RFC 3161, 2.3) ;
- SIGNATURE_AND_CHAIN : signature du jeton et chaîne de certificats jusqu'à une racine
  de confiance, certificats valides à la date d'horodatage. Ce contrôle est délégué au
  Verifier de rfc3161-client : la cryptographie n'est jamais réimplémentée ici.

Contrôle informatif :
- REVOCATION : UNKNOWN. La révocation des certificats n'est pas consultable hors ligne ;
  le résultat ne prétend jamais qu'elle a été vérifiée.
"""

import contextlib
import hmac
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from cryptography import x509
from rfc3161_client import PKIStatus, VerifierBuilder, decode_timestamp_response
from rfc3161_client import _rust as rfc3161_internal

from veritas_verifier.hash_service import normalize_digest

SHA256_OID = x509.ObjectIdentifier("2.16.840.1.101.3.4.2.1")


class Check(StrEnum):
    RESPONSE_READABLE = "RESPONSE_READABLE"
    STATUS_GRANTED = "STATUS_GRANTED"
    MESSAGE_IMPRINT = "MESSAGE_IMPRINT"
    REQUEST_MATCH = "REQUEST_MATCH"
    NONCE = "NONCE"
    TSA_CERTIFICATE = "TSA_CERTIFICATE"
    SIGNATURE_AND_CHAIN = "SIGNATURE_AND_CHAIN"
    REVOCATION = "REVOCATION"


MANDATORY = tuple(check for check in Check if check is not Check.REVOCATION)


class CheckStatus(StrEnum):
    PASS = "PASS"  # noqa: S105 - verdict de contrôle, pas un mot de passe
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CheckResult:
    check: Check
    status: CheckStatus
    detail: str = ""


@dataclass(frozen=True)
class TimestampVerification:
    """Résultat complet. `valid` seulement si tous les contrôles obligatoires sont PASS."""

    checks: list[CheckResult]
    generation_time: datetime | None = None
    serial_number: str | None = None
    policy_oid: str | None = None
    tsa_subject: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        by_check = {result.check: result.status for result in self.checks}
        return all(by_check.get(check) is CheckStatus.PASS for check in MANDATORY)

    def status_of(self, check: Check) -> CheckStatus | None:
        return next((r.status for r in self.checks if r.check is check), None)


def _same_bytes(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)


def _signer_certificate(response) -> x509.Certificate | None:
    """Certificat désigné par le SignerInfo (issuerAndSerialNumber), qui est couvert par
    la signature : on ne se fie pas à l'ordre des certificats joints."""
    signer_infos = list(response.signed_data.signer_infos)
    if len(signer_infos) != 1:
        return None
    signer = signer_infos[0]
    for der in response.signed_data.certificates:
        certificate = x509.load_der_x509_certificate(der)
        same_issuer = certificate.issuer == signer.issuer
        if same_issuer and certificate.serial_number == signer.serial_number:
            return certificate
    return None


def _tsa_certificate_check(certificate: x509.Certificate | None) -> CheckResult:
    if certificate is None:
        return CheckResult(Check.TSA_CERTIFICATE, CheckStatus.FAIL, "Certificat signataire absent.")
    try:
        eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    except x509.ExtensionNotFound:
        return CheckResult(Check.TSA_CERTIFICATE, CheckStatus.FAIL, "Usage étendu absent.")
    except Exception:  # noqa: BLE001 - certificat malformé (il est décodé à la demande)
        return CheckResult(Check.TSA_CERTIFICATE, CheckStatus.FAIL, "Certificat illisible.")
    if not eku.critical or x509.ExtendedKeyUsageOID.TIME_STAMPING not in eku.value:
        return CheckResult(
            Check.TSA_CERTIFICATE, CheckStatus.FAIL, "Usage critique id-kp-timeStamping absent."
        )
    return CheckResult(Check.TSA_CERTIFICATE, CheckStatus.PASS)


def verify_timestamp_token(
    response_der: bytes,
    request_der: bytes,
    expected_digest: str,
    trust_roots: Sequence[x509.Certificate],
) -> TimestampVerification:
    """Vérifie que `response_der` est un jeton RFC 3161 valide pour `expected_digest`
    (SHA-256, hexadécimal), émis en réponse à `request_der`, par une TSA dont la chaîne
    remonte à l'une des `trust_roots`."""
    checks: list[CheckResult] = []
    expected = bytes.fromhex(normalize_digest(expected_digest))

    try:
        response = decode_timestamp_response(response_der)
    except Exception as error:  # noqa: BLE001 - toute erreur d'analyse = jeton illisible
        checks.append(CheckResult(Check.RESPONSE_READABLE, CheckStatus.FAIL, str(error)[:200]))
        checks += [CheckResult(c, CheckStatus.FAIL, "Réponse illisible.") for c in MANDATORY[1:]]
        checks.append(CheckResult(Check.REVOCATION, CheckStatus.UNKNOWN, "Non vérifiable."))
        return TimestampVerification(checks=checks)
    checks.append(CheckResult(Check.RESPONSE_READABLE, CheckStatus.PASS))

    granted = response.status == PKIStatus.GRANTED
    checks.append(
        CheckResult(
            Check.STATUS_GRANTED,
            CheckStatus.PASS if granted else CheckStatus.FAIL,
            "" if granted else f"Statut {PKIStatus(response.status).name}.",
        )
    )

    try:
        info = response.tst_info
    except Exception:  # noqa: BLE001 - refus de la TSA : pas de jeton
        info = None
    if info is None:
        checks += [
            CheckResult(c, CheckStatus.FAIL, "Aucun jeton dans la réponse.") for c in MANDATORY[2:]
        ]
        checks.append(CheckResult(Check.REVOCATION, CheckStatus.UNKNOWN, "Non vérifiable."))
        return TimestampVerification(checks=checks)

    try:
        imprint = info.message_imprint
        imprint_ok = imprint.hash_algorithm == SHA256_OID and _same_bytes(imprint.message, expected)
    except Exception:  # noqa: BLE001
        imprint_ok = False
    checks.append(
        CheckResult(
            Check.MESSAGE_IMPRINT,
            CheckStatus.PASS if imprint_ok else CheckStatus.FAIL,
            "" if imprint_ok else "L'empreinte horodatée n'est pas l'empreinte attendue.",
        )
    )

    try:
        request = rfc3161_internal.parse_timestamp_request(request_der)
    except Exception:  # noqa: BLE001
        request = None
    request_ok = (
        request is not None
        and request.message_imprint.hash_algorithm == SHA256_OID
        and _same_bytes(request.message_imprint.message, expected)
    )
    checks.append(
        CheckResult(
            Check.REQUEST_MATCH,
            CheckStatus.PASS if request_ok else CheckStatus.FAIL,
            "" if request_ok else "Requête illisible ou pour une autre empreinte.",
        )
    )
    try:
        nonce_ok = request is not None and request.nonce is not None and info.nonce == request.nonce
    except Exception:  # noqa: BLE001
        nonce_ok = False
    checks.append(
        CheckResult(
            Check.NONCE,
            CheckStatus.PASS if nonce_ok else CheckStatus.FAIL,
            "" if nonce_ok else "Nonce absent ou différent de celui de la requête.",
        )
    )

    try:
        signer = _signer_certificate(response)
    except Exception:  # noqa: BLE001 - structure ou certificat malformé : pas de signataire
        signer = None
    checks.append(_tsa_certificate_check(signer))

    if not trust_roots:
        chain = CheckResult(Check.SIGNATURE_AND_CHAIN, CheckStatus.FAIL, "Aucune racine.")
    else:
        builder = VerifierBuilder(roots=list(trust_roots))
        try:
            builder.build().verify(response, expected)
            chain = CheckResult(Check.SIGNATURE_AND_CHAIN, CheckStatus.PASS)
        except Exception as error:  # noqa: BLE001 - tout échec de vérification est un FAIL
            chain = CheckResult(Check.SIGNATURE_AND_CHAIN, CheckStatus.FAIL, str(error)[:200])
    checks.append(chain)

    checks.append(
        CheckResult(
            Check.REVOCATION,
            CheckStatus.UNKNOWN,
            "Révocation non consultable hors ligne (OCSP/CRL après le MVP).",
        )
    )
    details: dict = {}
    # Champs illisibles : laissés vides (le verdict, lui, est déjà établi ci-dessus).
    with contextlib.suppress(Exception):
        details["generation_time"] = info.gen_time
        details["serial_number"] = format(info.serial_number, "x")
        details["policy_oid"] = info.policy.dotted_string if info.policy else None
    with contextlib.suppress(Exception):
        details["tsa_subject"] = signer.subject.rfc4514_string() if signer else None
    return TimestampVerification(checks=checks, **details)
