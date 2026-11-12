"""Calcul et vérification d'empreintes SHA-256.

Le calcul se fait en flux, par blocs de 1 Mo : un fichier de plusieurs gigaoctets
n'est jamais chargé entièrement en mémoire.

Ce module ne dépend d'aucun autre module de VERITAS. Il sera partagé avec le
vérificateur autonome, qui doit produire exactement les mêmes empreintes.
"""

import hashlib
import hmac
from pathlib import Path
from typing import BinaryIO

ALGORITHM = "SHA-256"
ENCODING = "hex"
ENGINE_VERSION = "1.0"
CHUNK_SIZE = 1024 * 1024  # 1 Mo


def sha256_stream(stream: BinaryIO, chunk_size: int = CHUNK_SIZE) -> str:
    """Calcule l'empreinte d'un flux binaire déjà ouvert, sans le fermer."""
    digest = hashlib.sha256()
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: str | Path, chunk_size: int = CHUNK_SIZE) -> str:
    """Calcule l'empreinte d'un fichier sur disque (hexadécimal, minuscules)."""
    with Path(path).open("rb") as stream:
        return sha256_stream(stream, chunk_size)


def normalize_digest(digest: str) -> str:
    """Met une empreinte au format canonique et refuse toute valeur malformée."""
    candidate = digest.strip().lower()
    if len(candidate) != 64 or any(c not in "0123456789abcdef" for c in candidate):
        raise ValueError("Une empreinte SHA-256 compte exactement 64 caractères hexadécimaux.")
    return candidate


def digests_match(expected: str, calculated: str) -> bool:
    """Compare deux empreintes en temps constant."""
    return hmac.compare_digest(normalize_digest(expected), normalize_digest(calculated))


def verify_file(path: str | Path, expected_digest: str) -> bool:
    """Recalcule l'empreinte d'un fichier et la compare à la valeur attendue."""
    return digests_match(expected_digest, sha256_file(path))
