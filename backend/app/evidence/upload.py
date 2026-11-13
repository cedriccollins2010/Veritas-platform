"""Réception d'un fichier téléversé (multipart/form-data), au fil de l'eau.

Pourquoi ne pas utiliser UploadFile de FastAPI : il lit d'abord toute la requête,
puis rend la main. Un fichier de 5 Go serait donc entièrement reçu avant d'être refusé.
Ici, l'analyseur de python-multipart (déjà installé avec FastAPI) traite chaque
morceau dès son arrivée :
- la taille est comptée en continu, et la réception s'arrête dès que la limite est
  dépassée (413) ;
- chaque morceau est haché (SHA-256) et écrit dans un fichier temporaire, puis oublié :
  la mémoire utilisée ne dépend pas de la taille du fichier ;
- le contenu n'est jamais interprété : seuls ses octets bruts sont hachés et copiés.

Champs acceptés : « file » (obligatoire, un seul) et « title » (facultatif).
"""

import contextlib
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from app.crypto.hash_service import IncrementalSha256

FILE_FIELD = "file"
TITLE_FIELD = "title"
TITLE_MAX_LENGTH = 255
FILENAME_MAX_LENGTH = 255
MEDIA_TYPE_MAX_LENGTH = 255
DEFAULT_MEDIA_TYPE = "application/octet-stream"
# Marge pour les en-têtes multipart et le champ « title » autour du fichier.
ENVELOPE_ALLOWANCE = 64 * 1024
MAX_PARTS = 4
# Les morceaux sont regroupés par 1 Mo avant d'être hachés et écrits.
FLUSH_THRESHOLD = 1024 * 1024

_MEDIA_TYPE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*")


class UploadTooLargeError(Exception):
    """Le fichier dépasse la taille maximale autorisée."""


class InvalidUploadError(Exception):
    """Requête de téléversement mal formée."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ReceivedUpload:
    """Fichier reçu, haché et posé dans un fichier temporaire (à supprimer après usage)."""

    path: Path
    size: int
    sha256: str
    original_filename: str
    media_type: str
    title: str | None
    received_at: datetime

    def discard(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()


def clean_filename(raw: bytes) -> str:
    """Nom d'origine, conservé comme simple information (jamais comme chemin).

    On garde la dernière partie après « / » ou « \\ » (certains navigateurs envoient le
    chemin complet), on retire les caractères de contrôle et on tronque à 255.
    """
    name = raw.decode("utf-8", errors="replace")
    name = re.split(r"[/\\]", name)[-1]
    name = "".join(c for c in name if unicodedata.category(c)[0] != "C").strip()
    name = name[:FILENAME_MAX_LENGTH]
    return name if name and name not in {".", ".."} else "fichier"


def clean_media_type(raw: str | None) -> str:
    """Type déclaré par le client. Information seulement : il n'est pas vérifié ici et
    ne sert jamais à interpréter le fichier."""
    if not raw:
        return DEFAULT_MEDIA_TYPE
    media_type = raw.split(";")[0].strip().lower()
    if len(media_type) > MEDIA_TYPE_MAX_LENGTH or not _MEDIA_TYPE.fullmatch(media_type):
        return DEFAULT_MEDIA_TYPE
    return media_type


@dataclass
class _Receiver:
    """État de l'analyse, mis à jour par les rappels de l'analyseur multipart."""

    max_file_bytes: int
    hasher: IncrementalSha256 = field(default_factory=IncrementalSha256)
    pending: bytearray = field(default_factory=bytearray)
    size: int = 0
    parts: int = 0
    current: str | None = None
    header_field: bytearray = field(default_factory=bytearray)
    header_value: bytearray = field(default_factory=bytearray)
    headers: dict[str, bytes] = field(default_factory=dict)
    file_seen: bool = False
    file_complete: bool = False
    finished: bool = False
    filename: str = ""
    media_type: str = DEFAULT_MEDIA_TYPE
    title: bytearray | None = None

    def on_part_begin(self) -> None:
        self.parts += 1
        if self.parts > MAX_PARTS:
            raise InvalidUploadError("Trop de champs dans le formulaire.")
        self.headers = {}
        self.current = None

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self.header_field += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self.header_value += data[start:end]

    def on_header_end(self) -> None:
        self.headers[bytes(self.header_field).decode("latin-1").lower()] = bytes(self.header_value)
        self.header_field.clear()
        self.header_value.clear()

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self.headers.get("content-disposition", b""))
        name = options.get(b"name", b"").decode("utf-8", errors="replace")
        if b"filename" in options:
            if name != FILE_FIELD:
                raise InvalidUploadError(f"Fichier attendu dans le champ « {FILE_FIELD} ».")
            if self.file_seen:
                raise InvalidUploadError("Un seul fichier par preuve.")
            self.file_seen = True
            self.filename = clean_filename(options[b"filename"])
            content_type = self.headers.get("content-type", b"").decode("latin-1")
            self.media_type = clean_media_type(content_type)
            self.current = FILE_FIELD
        elif name == TITLE_FIELD and self.title is None:
            self.title = bytearray()
            self.current = TITLE_FIELD
        else:
            raise InvalidUploadError(f"Champ inattendu : « {name} ».")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        piece = data[start:end]
        if self.current == FILE_FIELD:
            self.size += len(piece)
            if self.size > self.max_file_bytes:
                raise UploadTooLargeError
            self.pending += piece
        elif self.current == TITLE_FIELD and self.title is not None:
            self.title += piece
            if len(self.title) > TITLE_MAX_LENGTH * 4:  # 4 octets max par caractère
                raise InvalidUploadError("Titre trop long.")

    def on_part_end(self) -> None:
        if self.current == FILE_FIELD:
            self.file_complete = True
        self.current = None

    def on_end(self) -> None:
        # Appelé seulement quand la frontière finale « --boundary-- » a été lue.
        self.finished = True

    def callbacks(self) -> dict:
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
            "on_end": self.on_end,
        }

    def decoded_title(self) -> str | None:
        if self.title is None:
            return None
        try:
            title = self.title.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise InvalidUploadError("Titre : encodage UTF-8 attendu.") from error
        if len(title) > TITLE_MAX_LENGTH:
            raise InvalidUploadError("Titre trop long.")
        if any(unicodedata.category(c)[0] == "C" for c in title):
            # Caractères de contrôle (NUL, saut de ligne...) : refusés plutôt que retirés
            # en silence, le titre étant saisi par l'analyste.
            raise InvalidUploadError("Titre : caractères de contrôle interdits.")
        return title or None


def _flush(receiver: _Receiver, output) -> None:
    """Hache et écrit les octets en attente (exécuté hors de la boucle asynchrone)."""
    if receiver.pending:
        receiver.hasher.update(receiver.pending)
        output.write(receiver.pending)
        receiver.pending.clear()


async def receive_upload(
    request: Request, *, max_file_bytes: int, temp_dir: Path | None = None
) -> ReceivedUpload:
    """Lit la requête jusqu'au bout, ou s'arrête à la première erreur.

    En cas d'erreur, le fichier temporaire est supprimé avant de propager l'exception.
    """
    content_type, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise InvalidUploadError("multipart/form-data attendu.", status_code=415)

    max_body_bytes = max_file_bytes + ENVELOPE_ALLOWANCE
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_body_bytes:
        # Taille annoncée trop grande : refus immédiat, sans rien lire.
        raise UploadTooLargeError

    receiver = _Receiver(max_file_bytes=max_file_bytes)
    parser = MultipartParser(boundary, receiver.callbacks())
    descriptor, temporary = tempfile.mkstemp(prefix="veritas-upload-", dir=temp_dir)
    path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as output:
            received = 0
            async for chunk in request.stream():
                received += len(chunk)
                if received > max_body_bytes:
                    raise UploadTooLargeError
                try:
                    parser.write(chunk)
                except MultipartParseError as error:
                    raise InvalidUploadError("Formulaire multipart mal formé.") from error
                if len(receiver.pending) >= FLUSH_THRESHOLD:
                    # Hachage et écriture dans un fil séparé : la boucle asynchrone
                    # reste libre pour les autres requêtes pendant un gros dépôt.
                    await run_in_threadpool(_flush, receiver, output)
            try:
                parser.finalize()
            except MultipartParseError as error:
                raise InvalidUploadError("Formulaire multipart mal formé.") from error
            await run_in_threadpool(_flush, receiver, output)
            # Pas de fsync : ce fichier est temporaire. C'est le stockage qui garantit
            # que l'original est bien écrit sur le disque.
            await run_in_threadpool(output.flush)
        if not receiver.file_seen:
            raise InvalidUploadError(f"Champ « {FILE_FIELD} » manquant.", status_code=422)
        if not (receiver.file_complete and receiver.finished):
            # La requête s'est terminée avant la fin du formulaire (connexion coupée,
            # envoi tronqué). La finalisation de python-multipart ne le signale pas :
            # sans ce contrôle, un fichier partiel serait enregistré comme preuve.
            raise InvalidUploadError("Envoi incomplet : la fin du formulaire n'a pas été reçue.")
        return ReceivedUpload(
            path=path,
            size=receiver.size,
            sha256=receiver.hasher.hexdigest(),
            original_filename=receiver.filename,
            media_type=receiver.media_type,
            title=receiver.decoded_title(),
            received_at=datetime.now(UTC),
        )
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        raise
