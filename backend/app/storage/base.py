"""Interface commune des stockages de fichiers.

Le reste du code ne connaît que `Storage` : passer du disque local à un stockage
compatible S3 ne change rien ailleurs (choix par la variable STORAGE_BACKEND).

Trois règles valent pour toutes les implémentations :
1. Les clés sont générées par le serveur (new_storage_key), jamais dérivées du nom de
   fichier fourni par l'utilisateur. Le nom d'origine est conservé en base
   (evidence_files.original_filename), pas dans le stockage.
2. Toute clé est validée (validate_key) : pas de « .. », pas de chemin absolu, un
   alphabet restreint. Un nom comme « ../../etc/passwd » est refusé avant tout accès.
3. Un fichier n'est jamais réécrit : enregistrer une clé qui existe déjà lève
   StorageKeyExistsError, et le contenu d'origine reste intact.
"""

import re
import uuid
from abc import ABC, abstractmethod
from typing import BinaryIO

CHUNK_SIZE = 1024 * 1024  # 1 Mo, comme le calcul d'empreinte

# Segments séparés par « / » ; chaque segment commence par une lettre minuscule ou un
# chiffre (donc jamais par un point : ni « .. », ni fichier caché).
_KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]*(/[a-z0-9][a-z0-9_.-]*)*")
KEY_MAX_LENGTH = 512  # longueur de evidence_files.storage_key


class StorageError(Exception):
    """Erreur de stockage."""


class InvalidStorageKeyError(StorageError, ValueError):
    """Clé mal formée ou dangereuse."""


class StorageKeyExistsError(StorageError):
    """La clé existe déjà : un fichier stocké n'est jamais remplacé."""


class StorageKeyNotFoundError(StorageError, FileNotFoundError):
    """Aucun fichier pour cette clé."""


def new_storage_key(prefix: str = "originals", suffix: str = "") -> str:
    """Clé unique générée par le serveur : « originals/<uuid4> », ou par exemple
    « timestamps/<uuid4>.tsr » avec un suffixe."""
    key = f"{prefix}/{uuid.uuid4()}{suffix}"
    validate_key(key)
    return key


def validate_key(key: str) -> str:
    if (
        not isinstance(key, str)
        or len(key) > KEY_MAX_LENGTH
        or ".." in key
        or _KEY_PATTERN.fullmatch(key) is None
    ):
        raise InvalidStorageKeyError(f"Clé de stockage refusée : {key!r}")
    return key


class Storage(ABC):
    @abstractmethod
    def save_stream(self, key: str, stream: BinaryIO) -> int:
        """Enregistre le contenu du flux sous `key` et retourne le nombre d'octets écrits.

        Lève StorageKeyExistsError si la clé existe déjà. En cas d'erreur pendant
        l'écriture, aucun fichier partiel n'est visible sous `key`.
        """

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Ouvre le fichier en lecture binaire (à utiliser avec « with »)."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def size(self, key: str) -> int:
        """Taille en octets. Lève StorageKeyNotFoundError si la clé n'existe pas."""
