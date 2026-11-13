"""Tests du client RFC 3161 (issue #23).

Aucune TSA réelle n'est appelée (sauf le test marqué tsa_live) : une autorité
d'horodatage de test est créée localement avec OpenSSL (autorité racine + certificat de
TSA), et répond à de vraies requêtes par de vrais jetons signés.
"""

import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
from rfc3161_client import PKIStatus, decode_timestamp_response

from app.core.config import Settings
from app.storage.local import LocalStorage
from app.timestamp.provider import (
    RESPONSE_MEDIA_TYPE,
    HttpTimestampProvider,
    TsaProtocolError,
    TsaRejectedError,
    TsaResponseMismatchError,
    TsaUnavailableError,
)
from app.timestamp.request import TimestampRequestError, build_request
from app.timestamp.service import create_provider, store_exchange
from tests.local_tsa import OPENSSL, LocalTsa, run_openssl

needs_openssl = pytest.mark.skipif(OPENSSL is None, reason="openssl absent")
DIGEST = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"  # SHA-256("abc")
OTHER_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _run(*args: str, cwd: Path) -> bytes:
    return run_openssl(*args, cwd=cwd)


def _provider(handler, timeout: float = 5.0) -> HttpTimestampProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpTimestampProvider(
        "TSA de test", "https://tsa.test/tsr", timeout_seconds=timeout, client=client
    )


def _tsa_handler(tsa: LocalTsa):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"] == "application/timestamp-query"
        return httpx.Response(
            200, headers={"Content-Type": RESPONSE_MEDIA_TYPE}, content=tsa.reply(request.content)
        )

    return handler


# --- Construction de la requête ------------------------------------------------------


@needs_openssl
def test_request_is_identical_to_openssl(tmp_path) -> None:
    """Même requête qu'OpenSSL, octet pour octet (sans nonce, qu'OpenSSL tire au hasard)."""
    expected = _run(
        "ts", "-query", "-digest", DIGEST, "-sha256", "-cert", "-no_nonce", cwd=tmp_path
    )
    assert build_request(DIGEST, nonce=None) == expected


def test_request_is_identical_to_rfc3161_client() -> None:
    """Même requête que rfc3161-client, nonce compris, pour les mêmes données."""
    import rfc3161_client
    from rfc3161_client import _rust

    reference = (
        rfc3161_client.TimestampRequestBuilder()
        .data(b"abc")
        .hash_algorithm(rfc3161_client.HashAlgorithm.SHA256)
        .build()
        .as_bytes()
    )
    nonce = _rust.parse_timestamp_request(reference).nonce
    assert build_request(DIGEST, nonce=nonce) == reference


@pytest.mark.parametrize("nonce", [1, 127, 128, 255, 256, 2**63, 2**64 - 1])
def test_nonce_edge_cases_are_encoded_correctly(nonce: int) -> None:
    """Entiers DER : le bit de poids fort impose un octet nul en tête (relu par la
    bibliothèque à chaque construction)."""
    build_request(DIGEST, nonce=nonce)


@pytest.mark.parametrize("digest", ["", "abc", DIGEST[:-1], "z" * 64])
def test_malformed_digest_is_refused(digest: str) -> None:
    with pytest.raises(ValueError):
        build_request(digest, nonce=1)


def test_negative_nonce_is_refused() -> None:
    with pytest.raises(TimestampRequestError):
        build_request(DIGEST, nonce=-1)


# --- Échange avec la TSA de test -----------------------------------------------------


def test_timestamp_from_local_tsa_is_genuine(tsa: LocalTsa) -> None:
    exchange = _provider(_tsa_handler(tsa)).request_timestamp(DIGEST.upper())

    assert exchange.digest == DIGEST
    decoded = decode_timestamp_response(exchange.response)
    assert decoded.status == PKIStatus.GRANTED
    assert decoded.tst_info.nonce == exchange.nonce
    assert decoded.tst_info.message_imprint.message.hex() == DIGEST
    # Vérification indépendante par OpenSSL : le jeton reçu est authentique.
    assert tsa.verify_with_openssl(exchange.response, DIGEST)
    assert not tsa.verify_with_openssl(exchange.response, OTHER_DIGEST)


def test_each_request_has_a_fresh_nonce(tsa: LocalTsa) -> None:
    provider = _provider(_tsa_handler(tsa))
    nonces = {provider.request_timestamp(DIGEST).nonce for _ in range(5)}
    assert len(nonces) == 5


def test_rejection_is_reported(tsa: LocalTsa, tmp_path) -> None:
    # La TSA de test n'accepte que SHA-256 : sa réponse à une requête SHA-1 est un refus.
    sha1_query = _run(
        "ts",
        "-query",
        "-digest",
        "a9993e364706816aba3e25717850c26c9cd0d89d",
        "-sha1",
        "-no_nonce",
        cwd=tmp_path,
    )
    rejection = tsa.reply(sha1_query)
    provider = _provider(
        lambda r: httpx.Response(
            200, headers={"Content-Type": RESPONSE_MEDIA_TYPE}, content=rejection
        )
    )
    with pytest.raises(TsaRejectedError):
        provider.request_timestamp(DIGEST)


def test_response_to_another_request_is_refused(tsa: LocalTsa) -> None:
    """Une réponse rejouée (nonce différent) ou pour une autre empreinte est refusée."""
    replayed = tsa.reply(build_request(DIGEST, nonce=12345))

    def wrong_nonce(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": RESPONSE_MEDIA_TYPE}, content=replayed)

    with pytest.raises(TsaResponseMismatchError, match="nonce"):
        _provider(wrong_nonce).request_timestamp(DIGEST)

    from rfc3161_client import _rust

    def wrong_digest(request: httpx.Request) -> httpx.Response:
        nonce = _rust.parse_timestamp_request(request.content).nonce
        return httpx.Response(
            200,
            headers={"Content-Type": RESPONSE_MEDIA_TYPE},
            content=tsa.reply(build_request(OTHER_DIGEST, nonce=nonce)),
        )

    with pytest.raises(TsaResponseMismatchError, match="empreinte"):
        _provider(wrong_digest).request_timestamp(DIGEST)


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(500, headers={"Content-Type": RESPONSE_MEDIA_TYPE}), "HTTP 500"),
        (httpx.Response(302, headers={"Location": "https://ailleurs.test/"}), "HTTP 302"),
        (
            httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>"),
            "type de réponse",
        ),
        (
            httpx.Response(200, headers={"Content-Type": RESPONSE_MEDIA_TYPE}, content=b"\x30\x00"),
            "illisible",
        ),
        (
            httpx.Response(
                200, headers={"Content-Type": RESPONSE_MEDIA_TYPE}, content=b"\x30" * (65 * 1024)
            ),
            "anormalement grande",
        ),
    ],
    ids=["http-500", "redirection", "html", "illisible", "trop-grande"],
)
def test_abnormal_responses_are_typed_errors(response, reason) -> None:
    """Chaque anomalie est refusée pour SA raison (pas par hasard plus loin)."""
    with pytest.raises(TsaProtocolError, match=reason):
        _provider(lambda r: response).request_timestamp(DIGEST)


def test_unreachable_tsa_is_reported() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connexion refusée", request=request)

    with pytest.raises(TsaUnavailableError):
        _provider(refuse).request_timestamp(DIGEST)


def test_silent_tsa_times_out_quickly() -> None:
    """Un vrai serveur qui accepte la connexion mais ne répond jamais : l'erreur arrive
    en moins du délai configuré (plus une marge), jamais d'attente infinie."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    connections = []
    threading.Thread(target=lambda: connections.append(server.accept()), daemon=True).start()

    provider = HttpTimestampProvider(
        "TSA muette",
        f"http://127.0.0.1:{port}/tsr",
        timeout_seconds=0.5,
        client=httpx.Client(trust_env=False),
    )
    start = time.monotonic()
    try:
        with pytest.raises(TsaUnavailableError, match="délai"):
            provider.request_timestamp(DIGEST)
    finally:
        server.close()
    assert time.monotonic() - start < 2.0


# --- Conservation et configuration ---------------------------------------------------


def test_exchange_is_stored_byte_for_byte(tsa: LocalTsa, tmp_path) -> None:
    exchange = _provider(_tsa_handler(tsa)).request_timestamp(DIGEST)
    storage = LocalStorage(tmp_path / "storage")
    stored = store_exchange(storage, exchange)
    assert stored.request_key.startswith("timestamps/") and stored.request_key.endswith(".tsq")
    assert stored.response_key.endswith(".tsr")
    with storage.open(stored.request_key) as request, storage.open(stored.response_key) as resp:
        assert (request.read(), resp.read()) == (exchange.request, exchange.response)


def test_provider_is_chosen_by_configuration() -> None:
    assert create_provider(Settings()).url == "http://timestamp.digicert.com"
    freetsa = create_provider(Settings(tsa_provider="freetsa", tsa_timeout_seconds=3))
    assert (freetsa.name, freetsa.url) == ("FreeTSA", "https://freetsa.org/tsr")


# --- TSA réelle (T04) -----------------------------------------------------------------


def _freetsa_reachable() -> bool:
    try:
        httpx.head("https://freetsa.org/", timeout=5)
    except httpx.HTTPError:
        return False
    return True


@pytest.mark.tsa_live
def test_t04_real_token_from_freetsa() -> None:
    """T04 : un jeton RFC 3161 est reçu d'une vraie TSA. Ignoré sans accès au réseau."""
    if not _freetsa_reachable():
        pytest.skip("FreeTSA injoignable depuis cet environnement")
    exchange = create_provider(Settings(tsa_provider="freetsa")).request_timestamp(DIGEST)
    decoded = decode_timestamp_response(exchange.response)
    assert decoded.status in (PKIStatus.GRANTED, PKIStatus.GRANTED_WITH_MODS)
    assert decoded.tst_info.message_imprint.message.hex() == DIGEST
