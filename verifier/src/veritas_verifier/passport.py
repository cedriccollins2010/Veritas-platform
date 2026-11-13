"""Passeport de preuve « veritas-passport-v1 » : disposition et écriture de l'archive.

Référence d'implémentation de verifier/SPECIFICATION.md (sections 3 et 4). Le passeport est
une archive ZIP qui contient exactement :

- ``manifest.json`` : le manifeste 1.1, sous sa forme canonique RFC 8785 ;
- ``original/<file_id>`` : chaque fichier conservé (``storage_mode = STORED``) ;
- ``timestamp/<id>.tsr`` et ``timestamp/<id>.tsq`` : chaque jeton RFC 3161 et sa requête,
  aux chemins annoncés par le manifeste.

Rien d'autre : pas de copie de la chaîne de possession (elle est dans le manifeste), pas
de résultat de vérification, pas de racine de confiance. Le nom d'origine d'un fichier
n'est jamais un chemin dans l'archive.

L'écriture est déterministe : entrées triées, sans compression, date fixe, attributs fixes.
Deux exports du même état donnent la même archive, octet pour octet.
"""

import json
import re
import shutil
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

from veritas_verifier import canonical

FORMAT = "veritas-passport-v1"
MANIFEST_PATH = "manifest.json"
MANIFEST_FORMAT = "veritas-manifest"
# Versions du manifeste qu'un passeport v1 peut contenir.
MANIFEST_FORMAT_VERSIONS = frozenset({"1.1"})

ORIGINAL_DIR = "original"
TIMESTAMP_DIR = "timestamp"

# Limites de lecture (SPECIFICATION.md, section 3.3). Un vérificateur peut les relever
# explicitement ; il ne lit jamais une entrée plus grande que la taille attendue.
MAX_MANIFEST_SIZE = 16 * 1024 * 1024  # 16 Mio
MAX_TIMESTAMP_FILE_SIZE = 1024 * 1024  # 1 Mio par .tsr ou .tsq
MAX_ENTRIES = 10_000

# Attributs fixes de chaque entrée (SPECIFICATION.md, section 3.2).
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)  # plus petite date représentable en ZIP
ZIP_CREATE_SYSTEM = 3  # Unix, quel que soit le système qui écrit l'archive
ZIP_EXTERNAL_ATTR = 0o100644 << 16  # fichier ordinaire, rw-r--r--
COPY_CHUNK_SIZE = 1024 * 1024

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ENTRY_NAME = re.compile(
    rf"\A(?:manifest\.json|{ORIGINAL_DIR}/{_UUID}|{TIMESTAMP_DIR}/{_UUID}\.ts[qr])\Z"
)
_UUID_ONLY = re.compile(rf"\A{_UUID}\Z")


class PassportFormatError(ValueError):
    """Le contenu ne respecte pas le format veritas-passport-v1."""


def is_valid_entry_name(name: str) -> bool:
    """Seuls trois motifs de noms existent, en ASCII minuscule : ni chemin absolu, ni
    « .. », ni barre oblique inverse, ni nom choisi par l'utilisateur."""
    return isinstance(name, str) and ENTRY_NAME.fullmatch(name) is not None


def _uuid(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _UUID_ONLY.fullmatch(value):
        raise PassportFormatError(f"{what} : identifiant invalide.")
    return value


def original_path(file_id: str) -> str:
    return f"{ORIGINAL_DIR}/{_uuid(file_id, 'Fichier')}"


def timestamp_paths(timestamp_record_id: str) -> tuple[str, str]:
    """Chemins du jeton (.tsr) et de la requête (.tsq) d'un horodatage."""
    record_id = _uuid(timestamp_record_id, "Horodatage")
    return f"{TIMESTAMP_DIR}/{record_id}.tsr", f"{TIMESTAMP_DIR}/{record_id}.tsq"


def expected_entries(manifest: Mapping[str, Any]) -> frozenset[str]:
    """Ensemble exact des entrées d'un passeport, calculé à partir du manifeste seul.

    Lève PassportFormatError si le manifeste n'est pas d'une version admise ou si un
    chemin annoncé n'est pas le chemin canonique (``timestamp/<id>.tsr|.tsq``).
    """
    try:
        if manifest["format"] != MANIFEST_FORMAT:
            raise PassportFormatError("Ce n'est pas un manifeste VERITAS.")
        if manifest["format_version"] not in MANIFEST_FORMAT_VERSIONS:
            raise PassportFormatError(
                f"Version de manifeste {manifest['format_version']!r} non admise en {FORMAT}."
            )
        entries = {MANIFEST_PATH}
        for file in manifest["files"]:
            if file["storage_mode"] == "STORED":
                entries.add(original_path(file["id"]))
        for item in manifest["timestamps"]:
            token_path, request_path = timestamp_paths(item["timestamp_record_id"])
            if item["token"]["path"] != token_path or item["request"]["path"] != request_path:
                raise PassportFormatError("Chemin de jeton ou de requête non canonique.")
            entries.update((token_path, request_path))
    except (KeyError, TypeError) as error:
        raise PassportFormatError(f"Manifeste incomplet : {error!r}.") from error
    return frozenset(entries)


def _zip_info(name: str, size: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_DATE_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = ZIP_CREATE_SYSTEM
    info.external_attr = ZIP_EXTERNAL_ATTR
    info.file_size = size  # connu d'avance : ZIP64 seulement si la taille l'exige
    return info


def write_passport(destination: BinaryIO, entries: Mapping[str, bytes | Path]) -> None:
    """Écrit un passeport dans `destination` (fichier binaire ouvert, avec accès direct).

    `entries` associe chaque nom d'entrée à son contenu : des octets, ou le chemin d'un
    fichier sur disque (copié par blocs, jamais chargé entier en mémoire). Refuse
    d'écrire une archive qui ne serait pas un passeport v1 complet et exact : manifeste
    non canonique, entrée manquante ou en trop, nom non conforme.
    """
    if not destination.seekable():
        # Sans accès direct, zipfile ajoute des « data descriptors » : archive différente.
        raise PassportFormatError("La destination doit permettre l'accès direct (seek).")
    invalid = sorted(name for name in entries if not is_valid_entry_name(name))
    if invalid:
        raise PassportFormatError(f"Noms d'entrée non conformes : {invalid}.")
    manifest_bytes = entries.get(MANIFEST_PATH)
    if not isinstance(manifest_bytes, bytes):
        raise PassportFormatError("manifest.json doit être fourni sous forme d'octets.")
    try:
        manifest = json.loads(manifest_bytes)
        is_canonical = canonical.canonicalize(manifest) == manifest_bytes
    except (ValueError, canonical.NonCanonicalValueError) as error:
        raise PassportFormatError("manifest.json illisible.") from error
    if not is_canonical:
        raise PassportFormatError("manifest.json n'est pas sous forme canonique RFC 8785.")
    expected = expected_entries(manifest)
    if set(entries) != expected:
        missing = sorted(expected - set(entries))
        extra = sorted(set(entries) - expected)
        raise PassportFormatError(f"Entrées manquantes : {missing} ; en trop : {extra}.")

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        # Tri par octets du nom (ASCII) : un ordre unique, quelle que soit la plateforme.
        for name in sorted(entries):
            content = entries[name]
            if isinstance(content, bytes):
                with archive.open(_zip_info(name, len(content)), "w") as target:
                    target.write(content)
            else:
                path = Path(content)
                with path.open("rb") as source:
                    size = path.stat().st_size
                    with archive.open(_zip_info(name, size), "w") as target:
                        shutil.copyfileobj(source, target, COPY_CHUNK_SIZE)
