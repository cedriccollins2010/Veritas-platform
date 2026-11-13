"""Empreinte du manifeste (format « veritas-manifest » 1.0).

    manifest_digest.value = SHA-256( JCS(manifeste sans son champ « manifest_digest ») )

Le manifeste porte sa propre empreinte : un tiers retire le champ, recalcule
l'empreinte sur la forme canonique RFC 8785 du reste, et compare. Changer un seul
caractère du manifeste change cette empreinte.

L'empreinte du manifeste détecte une modification accidentelle ou maladroite ; elle ne
protège pas seule contre un faussaire qui recalculerait tout. Cette garantie viendra de
l'horodatage RFC 3161 du manifeste par une autorité externe (phase 3).

Ce module ne dépend pas du serveur VERITAS : le serveur et le vérificateur autonome
l'appellent tous deux.
"""

import hashlib
import json
from importlib import resources
from typing import Any

from veritas_verifier import canonical
from veritas_verifier.hash_service import ALGORITHM, digests_match

DIGEST_FIELD = "manifest_digest"
# Schéma JSON (draft 2020-12) de chaque version publiée, livré avec le paquet.
SCHEMA_FILES = {"1.0": "manifest-v1.schema.json", "1.1": "manifest-v1.1.schema.json"}


def load_schema(format_version: str) -> dict[str, Any]:
    """Schéma JSON publié pour une version du manifeste (KeyError si inconnue)."""
    schema = resources.files("veritas_verifier") / "schemas" / SCHEMA_FILES[format_version]
    return json.loads(schema.read_text(encoding="utf-8"))


def compute_digest(manifest: dict[str, Any]) -> str:
    """SHA-256 (hexadécimal) de la forme canonique du manifeste, sans manifest_digest."""
    body = {key: value for key, value in manifest.items() if key != DIGEST_FIELD}
    return hashlib.sha256(canonical.canonicalize(body)).hexdigest()


def seal(manifest: dict[str, Any]) -> dict[str, Any]:
    """Ajoute manifest_digest au manifeste (sans modifier l'original)."""
    sealed = {key: value for key, value in manifest.items() if key != DIGEST_FIELD}
    sealed[DIGEST_FIELD] = {
        "algorithm": ALGORITHM,
        "canonicalization": canonical.ALGORITHM,
        "value": compute_digest(sealed),
    }
    return sealed


def digest_is_valid(manifest: dict[str, Any]) -> bool:
    """Vrai si manifest_digest correspond au contenu. Ne lève jamais d'exception."""
    try:
        declared = manifest[DIGEST_FIELD]
        expected = (ALGORITHM, canonical.ALGORITHM)
        if (declared["algorithm"], declared["canonicalization"]) != expected:
            return False
        return digests_match(declared["value"], compute_digest(manifest))
    except (KeyError, TypeError, ValueError, canonical.NonCanonicalValueError):
        return False


def to_bytes(manifest: dict[str, Any]) -> bytes:
    """Octets publiés du manifeste : sa forme canonique RFC 8785 (UTF-8).

    Publier la forme canonique, plutôt qu'un JSON indenté, garantit que deux exports
    du même dossier sont identiques octet pour octet.
    """
    return canonical.canonicalize(manifest)
