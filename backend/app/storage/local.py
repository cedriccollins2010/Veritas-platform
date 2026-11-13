"""Stockage sur disque local, pour le développement, les tests et un serveur unique.

Écriture en deux temps pour qu'aucun fichier partiel ne soit jamais visible :
1. le flux est copié dans un fichier temporaire (dossier .incoming), puis forcé sur
   le disque (fsync) ;
2. le fichier est publié sous sa clé par un lien physique (os.link). Cette opération
   échoue si la clé existe déjà, de façon atomique : deux écritures simultanées de la
   même clé ne peuvent pas réussir toutes les deux, et rien n'est jamais écrasé.
Le fichier publié est ensuite mis en lecture seule.
"""

import contextlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from app.storage.base import (
    CHUNK_SIZE,
    Storage,
    StorageKeyExistsError,
    StorageKeyNotFoundError,
    validate_key,
)

_INCOMING = ".incoming"  # ne peut pas être une clé : les clés ne commencent pas par « . »


class LocalStorage(Storage):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        (self.root / _INCOMING).mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        # Deuxième barrière, au cas où la validation de la clé aurait une faille :
        # le chemin final doit rester dans le dossier de stockage.
        if not path.is_relative_to(self.root) or path == self.root:
            raise StorageKeyNotFoundError(key)
        return path

    def save_stream(self, key: str, stream: BinaryIO) -> int:
        final = self._path(key)
        if final.exists():
            raise StorageKeyExistsError(key)
        final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        descriptor, temporary = tempfile.mkstemp(dir=self.root / _INCOMING)
        try:
            written = 0
            with os.fdopen(descriptor, "wb") as output:
                while chunk := stream.read(CHUNK_SIZE):
                    output.write(chunk)
                    written += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, final)
            except FileExistsError as error:
                raise StorageKeyExistsError(key) from error
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
        final.chmod(0o440)  # lecture seule
        return written

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        try:
            return path.open("rb")
        except FileNotFoundError as error:
            raise StorageKeyNotFoundError(key) from error

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def size(self, key: str) -> int:
        path = self._path(key)
        try:
            return path.stat().st_size
        except FileNotFoundError as error:
            raise StorageKeyNotFoundError(key) from error
