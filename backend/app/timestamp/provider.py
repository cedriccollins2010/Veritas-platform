"""Fournisseurs d'horodatage RFC 3161 (autorités d'horodatage, « TSA »).

Le reste de VERITAS ne connaît que l'interface TimestampProvider : changer de TSA
(DigiCert, FreeTSA, plus tard un fournisseur sous contrat) ne change rien ailleurs.

Ce module ne connaît ni utilisateur ni organisation : il reçoit une empreinte et rend la
requête et la réponse brutes. La vérification complète du jeton (signature, chaîne de
certificats) est faite à part (issue #24) ; ici, on contrôle seulement que la réponse
est lisible, accordée, et qu'elle répond bien à CETTE requête (nonce et empreinte).
"""

from dataclasses import dataclass
from typing import Protocol

import httpx
from rfc3161_client import PKIStatus, decode_timestamp_response

from app.crypto.hash_service import digests_match, normalize_digest
from app.timestamp.request import build_request, new_nonce

REQUEST_MEDIA_TYPE = "application/timestamp-query"
RESPONSE_MEDIA_TYPE = "application/timestamp-reply"
# Une réponse RFC 3161 (jeton + certificats) pèse quelques Ko. Au-delà, c'est anormal :
# on refuse plutôt que de charger en mémoire ce qu'un serveur hostile enverrait.
MAX_RESPONSE_BYTES = 64 * 1024
_GRANTED = {PKIStatus.GRANTED, PKIStatus.GRANTED_WITH_MODS}


class TimestampError(Exception):
    """Échec d'horodatage. Le fichier et l'empreinte ne sont jamais perdus pour autant."""


class TsaUnavailableError(TimestampError):
    """TSA injoignable ou trop lente (délai dépassé) : réessayer plus tard."""


class TsaProtocolError(TimestampError):
    """Réponse HTTP anormale ou illisible."""


class TsaRejectedError(TimestampError):
    """La TSA a refusé la requête (statut RFC 3161 autre qu'« accordé »)."""


class TsaResponseMismatchError(TimestampError):
    """La réponse ne correspond pas à la requête envoyée (nonce ou empreinte)."""


@dataclass(frozen=True)
class TimestampExchange:
    """Requête et réponse brutes, à conserver octet pour octet."""

    tsa_name: str
    tsa_url: str
    digest: str
    nonce: int
    request: bytes
    response: bytes


class TimestampProvider(Protocol):
    name: str
    url: str

    def request_timestamp(self, digest_hex: str) -> TimestampExchange: ...


class HttpTimestampProvider:
    """TSA joignable en HTTP(S), protocole RFC 3161 « HTTP transport » (RFC 3161, 3.4).

    Le transport peut être en HTTP simple (c'est le cas de DigiCert) : le jeton est signé
    par la TSA, son intégrité ne dépend pas du canal, et seule l'empreinte est envoyée.
    """

    def __init__(
        self, name: str, url: str, *, timeout_seconds: float, client: httpx.Client | None = None
    ) -> None:
        self.name = name
        self.url = url
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client = client

    def request_timestamp(self, digest_hex: str) -> TimestampExchange:
        digest = normalize_digest(digest_hex)
        nonce = new_nonce()
        request = build_request(digest, nonce=nonce)
        response = self._post(request)
        self._check_response(response, digest, nonce)
        return TimestampExchange(
            tsa_name=self.name,
            tsa_url=self.url,
            digest=digest,
            nonce=nonce,
            request=request,
            response=response,
        )

    def _post(self, request: bytes) -> bytes:
        client = self._client or httpx.Client()
        try:
            with client.stream(
                "POST",
                self.url,
                content=request,
                headers={"Content-Type": REQUEST_MEDIA_TYPE, "Accept": RESPONSE_MEDIA_TYPE},
                timeout=self._timeout,
                follow_redirects=False,  # une redirection n'est pas suivie en silence
            ) as response:
                if response.status_code != 200:
                    raise TsaProtocolError(f"{self.name} : réponse HTTP {response.status_code}.")
                media_type = response.headers.get("content-type", "").split(";")[0].strip()
                if media_type.lower() != RESPONSE_MEDIA_TYPE:
                    raise TsaProtocolError(f"{self.name} : type de réponse inattendu.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise TsaProtocolError(f"{self.name} : réponse anormalement grande.")
                return bytes(body)
        except httpx.TimeoutException as error:
            raise TsaUnavailableError(f"{self.name} : délai dépassé.") from error
        except httpx.TransportError as error:
            raise TsaUnavailableError(f"{self.name} : injoignable ({error}).") from error
        finally:
            if self._client is None:
                client.close()

    def _check_response(self, response: bytes, digest: str, nonce: int) -> None:
        try:
            decoded = decode_timestamp_response(response)
        except Exception as error:  # noqa: BLE001 - toute erreur de décodage = illisible
            raise TsaProtocolError(f"{self.name} : réponse RFC 3161 illisible.") from error
        if decoded.status not in _GRANTED:
            raise TsaRejectedError(f"{self.name} : requête refusée (statut {decoded.status}).")
        info = decoded.tst_info
        if info.nonce != nonce:
            raise TsaResponseMismatchError(f"{self.name} : nonce différent de la requête.")
        if not digests_match(info.message_imprint.message.hex(), digest):
            raise TsaResponseMismatchError(f"{self.name} : empreinte différente de la requête.")
