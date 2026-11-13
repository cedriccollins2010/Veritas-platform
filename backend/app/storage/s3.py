"""Stockage compatible S3 (AWS S3 ou tout service qui parle le même protocole).

Le refus d'écraser repose sur l'écriture conditionnelle « If-None-Match: * » : le
service n'accepte l'objet que si la clé n'existe pas encore, et répond 412 sinon.
C'est atomique côté service. Le service choisi doit la prendre en charge ; la suite
de tests commune le vérifie (test « save_twice »).

Identifiants : jamais dans le code ni dans la configuration de VERITAS. boto3 les lit
dans les variables standard AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (ou un rôle).
"""

import contextlib
from typing import Any, BinaryIO

from botocore.exceptions import ClientError

from app.storage.base import Storage, StorageKeyExistsError, StorageKeyNotFoundError, validate_key

_ALREADY_EXISTS = {"PreconditionFailed", "ConditionalRequestConflict"}
_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


class S3Storage(Storage):
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def save_stream(self, key: str, stream: BinaryIO) -> int:
        """Le flux doit pouvoir être relu depuis le début (fichier temporaire, BytesIO) :
        le client S3 en calcule la longueur et la somme de contrôle avant l'envoi."""
        validate_key(key)
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=stream, IfNoneMatch="*")
        except ClientError as error:
            if _error_code(error) in _ALREADY_EXISTS:
                raise StorageKeyExistsError(key) from error
            raise
        return self.size(key)

    def _head(self, key: str) -> dict[str, Any]:
        validate_key(key)
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if _error_code(error) in _NOT_FOUND:
                raise StorageKeyNotFoundError(key) from error
            raise

    def open(self, key: str) -> BinaryIO:
        validate_key(key)
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except ClientError as error:
            if _error_code(error) in _NOT_FOUND:
                raise StorageKeyNotFoundError(key) from error
            raise
        return contextlib.closing(body)  # type: ignore[return-value]

    def exists(self, key: str) -> bool:
        try:
            self._head(key)
        except StorageKeyNotFoundError:
            return False
        return True

    def size(self, key: str) -> int:
        return int(self._head(key)["ContentLength"])
