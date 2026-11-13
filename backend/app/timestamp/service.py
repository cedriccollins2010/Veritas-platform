"""Fournisseur configuré et conservation des échanges avec la TSA."""

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

from app.core.config import Settings, get_settings
from app.storage import Storage, new_storage_key
from app.timestamp.provider import HttpTimestampProvider, TimestampExchange, TimestampProvider

# Adresses publiques des TSA prévues par le document de référence.
TSA_ENDPOINTS = {
    "digicert": ("DigiCert", "http://timestamp.digicert.com"),
    "freetsa": ("FreeTSA", "https://freetsa.org/tsr"),
}


def create_provider(settings: Settings) -> TimestampProvider:
    name, url = TSA_ENDPOINTS[settings.tsa_provider]
    return HttpTimestampProvider(name, url, timeout_seconds=settings.tsa_timeout_seconds)


@lru_cache
def get_timestamp_provider() -> TimestampProvider:
    return create_provider(get_settings())


@dataclass(frozen=True)
class StoredExchange:
    request_key: str
    response_key: str


def store_exchange(storage: Storage, exchange: TimestampExchange) -> StoredExchange:
    """Conserve la requête (.tsq) et la réponse (.tsr) originales, octet pour octet.

    Ce sont elles que le passeport de preuve embarquera : un tiers doit pouvoir refaire
    la vérification avec ses propres outils (openssl ts -verify).
    """
    request_key = new_storage_key("timestamps", suffix=".tsq")
    response_key = new_storage_key("timestamps", suffix=".tsr")
    storage.save_stream(request_key, BytesIO(exchange.request))
    storage.save_stream(response_key, BytesIO(exchange.response))
    return StoredExchange(request_key=request_key, response_key=response_key)
