"""Construction d'une requête d'horodatage RFC 3161 à partir d'une empreinte SHA-256.

Pourquoi ne pas utiliser TimestampRequestBuilder de rfc3161-client : il calcule lui-même
l'empreinte des données qu'on lui donne. Or VERITAS horodate une empreinte déjà calculée
(pendant la réception du fichier) ou déclarée par l'analyste (mode empreinte seule, sans
fichier). Décision documentée dans l'ADR-0008.

La requête est une petite structure ASN.1 fixe (RFC 3161, section 2.4.1), encodée ici en
DER. Ce n'est pas de la cryptographie, seulement de la mise en forme. Deux garde-fous :
- chaque requête produite est relue par l'analyseur de rfc3161-client, et ses champs
  comparés aux valeurs voulues, avant tout envoi ;
- les tests vérifient qu'elle est identique octet pour octet à celle d'OpenSSL
  (« openssl ts -query ») et à celle de rfc3161-client pour les mêmes données.

    TimeStampReq ::= SEQUENCE {
       version        INTEGER { v1(1) },
       messageImprint SEQUENCE { hashAlgorithm AlgorithmIdentifier, hashedMessage OCTET STRING },
       nonce          INTEGER OPTIONAL,
       certReq        BOOLEAN DEFAULT FALSE }
"""

import secrets

from cryptography.x509.oid import ObjectIdentifier

# rfc3161-client n'expose pas encore publiquement l'analyse d'une requête ; sa fonction
# interne est utilisée en garde-fou. La version de la bibliothèque est figée.
from rfc3161_client import _rust as rfc3161_internal

from app.crypto.hash_service import normalize_digest

SHA256_OID = ObjectIdentifier("2.16.840.1.101.3.4.2.1")
# AlgorithmIdentifier { id-sha256, NULL }, tel qu'OpenSSL et rfc3161-client l'encodent.
_SHA256_ALGORITHM = bytes.fromhex("300d06096086480165030402010500")
NONCE_BITS = 64


class TimestampRequestError(ValueError):
    """Requête impossible à construire ou incohérente après relecture."""


def _length(size: int) -> bytes:
    if size < 0x80:
        return bytes([size])
    encoded = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _length(len(content)) + content


def _integer(value: int) -> bytes:
    if value < 0:
        raise TimestampRequestError("Entier négatif interdit.")
    encoded = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    if encoded[0] & 0x80:  # DER : un entier positif ne doit pas avoir le bit de signe
        encoded = b"\x00" + encoded
    return _tlv(0x02, encoded)


def new_nonce() -> int:
    """Nonce aléatoire de 64 bits (jamais nul) : lie la réponse à cette requête précise."""
    while True:
        nonce = secrets.randbits(NONCE_BITS)
        if nonce:
            return nonce


def build_request(digest_hex: str, *, nonce: int | None, cert_req: bool = True) -> bytes:
    """Requête DER pour l'empreinte SHA-256 `digest_hex` (64 caractères hexadécimaux).

    cert_req : la TSA joint son certificat au jeton, pour que le jeton soit vérifiable seul.
    """
    digest = bytes.fromhex(normalize_digest(digest_hex))
    content = _integer(1) + _tlv(0x30, _SHA256_ALGORITHM + _tlv(0x04, digest))
    if nonce is not None:
        content += _integer(nonce)
    if cert_req:
        content += b"\x01\x01\xff"  # BOOLEAN TRUE (DER) ; FALSE est la valeur par défaut, omise
    request = _tlv(0x30, content)
    _check_request(request, digest, nonce, cert_req)
    return request


def _check_request(request: bytes, digest: bytes, nonce: int | None, cert_req: bool) -> None:
    """Relit la requête avec l'analyseur de rfc3161-client et compare chaque champ."""
    try:
        parsed = rfc3161_internal.parse_timestamp_request(request)
    except Exception as error:  # noqa: BLE001 - toute erreur d'analyse est un défaut
        raise TimestampRequestError(f"Requête illisible par rfc3161-client : {error}") from error
    if (
        parsed.version != 1
        or parsed.message_imprint.hash_algorithm != SHA256_OID
        or parsed.message_imprint.message != digest
        or parsed.nonce != nonce
        or bool(parsed.cert_req) != cert_req
    ):
        raise TimestampRequestError("La requête relue ne correspond pas aux valeurs voulues.")
