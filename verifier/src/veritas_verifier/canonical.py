"""Canonicalisation JSON selon la RFC 8785 (JSON Canonicalization Scheme, « JCS »).

Pourquoi : une empreinte se calcule sur des octets, et un même objet JSON peut s'écrire
de nombreuses façons (ordre des clés, espaces, écriture des nombres, échappements).
JCS en définit une seule. Le serveur et le vérificateur autonome produisent donc les
mêmes octets, donc la même empreinte.

Bibliothèque : rfc8785 (Trail of Bits). Ce module fait partie du paquet
veritas-verifier, partagé par le serveur et le vérificateur autonome.

Règle supplémentaire de VERITAS : pas de nombres à virgule dans les données hachées.
Leur représentation peut varier d'un système à l'autre (PostgreSQL JSONB, JavaScript) ;
les entiers, eux, sont limités à ±(2^53 - 1), la plage exacte en JSON (I-JSON, RFC 7493).
"""

from collections.abc import Mapping, Sequence
from typing import Any

import rfc8785

ALGORITHM = "JCS-RFC8785"  # valeur de custody_events.canonicalization
MAX_SAFE_INTEGER = 2**53 - 1


class NonCanonicalValueError(ValueError):
    """Valeur interdite dans des données hachées."""


def _check(value: Any, path: str) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise NonCanonicalValueError(f"{path} : entier hors de la plage exacte JSON")
        return
    if isinstance(value, float):
        raise NonCanonicalValueError(f"{path} : nombre à virgule interdit")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise NonCanonicalValueError(f"{path} : clé non textuelle")
            _check(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return
    raise NonCanonicalValueError(f"{path} : type {type(value).__name__} interdit")


def canonicalize(value: Any) -> bytes:
    """Octets canoniques (UTF-8) de `value`, après contrôle des types autorisés."""
    _check(value, "$")
    return rfc8785.dumps(value)
