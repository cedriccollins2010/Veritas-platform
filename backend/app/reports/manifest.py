"""Construction du manifeste JSON d'un dossier de preuve (format « veritas-manifest » 1.1).

Le manifeste décrit tout ce qu'un tiers doit vérifier : la preuve, ses fichiers et leurs
empreintes (avec leur origine), la chaîne de possession complète et sa tête, et les
versions des outils, et (depuis 1.1) les jetons d'horodatage vérifiés et l'ancrage de la
tête de chaîne. Schéma : documentation/api/manifest-v1.1.schema.json (le schéma 1.0 reste
publié tel quel : documentation/api/manifest-v1.schema.json).

Règle : le manifeste est une fonction de l'état enregistré, et de lui seul. Il ne contient
ni date de génération ni valeur aléatoire : deux exports du même dossier sont identiques
octet pour octet. created_at des événements (non haché) n'y figure pas.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

from veritas_verifier import canonical, custody_chain
from veritas_verifier import manifest as manifest_crypto
from veritas_verifier.hash_service import ENCODING, ENGINE_VERSION

from app import __version__
from app.custody.models import CustodyEvent
from app.evidence.models import EvidenceStatus, HashSource
from app.evidence.service import EvidenceView
from app.storage import Storage
from app.timestamp.models import TimestampPurpose, TimestampRecord, TimestampValidationStatus

FORMAT = "veritas-manifest"
FORMAT_VERSION = "1.1"

# Une preuve dont le dépôt a échoué ou n'est pas terminé n'a rien à décrire.
EXPORTABLE_STATUSES = frozenset(
    {
        EvidenceStatus.HASHED,
        EvidenceStatus.TIMESTAMP_PENDING,
        EvidenceStatus.CERTIFIED,
        EvidenceStatus.ARCHIVED,
    }
)


class EvidenceNotExportableError(Exception):
    """La preuve n'est pas dans un état qui permet de produire un manifeste."""


@dataclass(frozen=True)
class Manifest:
    document: dict[str, Any]
    content: bytes  # octets publiés : forme canonique RFC 8785

    @property
    def digest(self) -> str:
        return self.document[manifest_crypto.DIGEST_FIELD]["value"]


def _timestamp(value) -> str:
    return custody_chain.format_timestamp(value)


def _file_section(view: EvidenceView) -> list[dict[str, Any]]:
    file, hash_record = view.file, view.hash_record
    if file is None or hash_record is None:
        raise EvidenceNotExportableError("Preuve sans fichier ni empreinte.")
    source = HashSource(hash_record.source)
    return [
        {
            "id": str(file.id),
            "original_filename": file.original_filename,
            "media_type": file.media_type,
            "size": file.file_size,
            "storage_mode": file.storage_mode,
            "hashes": [
                {
                    "algorithm": hash_record.algorithm,
                    "encoding": hash_record.encoding,
                    "digest": hash_record.digest,
                    "engine_version": hash_record.engine_version,
                    "source": source.value,
                    # Même règle que l'API (ADR-0006) : vrai seulement si VERITAS a
                    # calculé l'empreinte sur le fichier reçu.
                    "verified_by_server": source is HashSource.SERVER,
                    "calculated_at": _timestamp(hash_record.calculated_at),
                }
            ],
        }
    ]


def _custody_section(events: list[CustodyEvent]) -> dict[str, Any]:
    if not events:
        raise EvidenceNotExportableError("Preuve sans chaîne de possession.")
    return {
        "format": custody_chain.FORMAT,
        "canonicalization": canonical.ALGORITHM,
        "hash_algorithm": "SHA-256",
        "genesis": custody_chain.GENESIS.hex(),
        "event_count": len(events),
        "head_hash": events[-1].event_hash,
        "events": [
            {
                "event_id": str(event.id),
                "sequence_number": event.sequence_number,
                "event_type": event.event_type,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "occurred_at": _timestamp(event.occurred_at),
                "event_data": event.event_data,
                "previous_event_hash": event.previous_event_hash,
                "event_hash": event.event_hash,
            }
            for event in events
        ],
    }


@dataclass(frozen=True)
class ManifestTimestamp:
    """Un jeton VALID et les empreintes des fichiers conservés (.tsr et .tsq)."""

    record: TimestampRecord
    token_sha256: str
    request_sha256: str


def collect_valid_timestamps(
    records: Sequence[TimestampRecord], storage: Storage
) -> list[ManifestTimestamp]:
    """Jetons vérifiés VALID, avec l'empreinte des fichiers réellement conservés.

    Seuls les jetons VALID figurent au manifeste : ce sont ceux qu'un tiers peut
    vérifier. Les tentatives en échec restent tracées dans la base et le journal.
    """
    collected = []
    for record in records:
        if record.validation_status != TimestampValidationStatus.VALID.value:
            continue
        with storage.open(record.token_storage_key) as token:
            token_sha256 = hashlib.sha256(token.read()).hexdigest()
        with storage.open(record.request_storage_key) as request:
            request_sha256 = hashlib.sha256(request.read()).hexdigest()
        collected.append(ManifestTimestamp(record, token_sha256, request_sha256))
    return collected


def _timestamp_entry(item: ManifestTimestamp) -> dict[str, Any]:
    record = item.record
    return {
        "timestamp_record_id": str(record.id),
        "purpose": record.purpose,
        "hash_algorithm": record.hash_algorithm,
        "message_imprint": record.message_imprint,
        "anchored_sequence_number": record.anchored_sequence_number,
        "tsa": {"name": record.tsa_name, "url": record.tsa_url},
        "policy_oid": record.policy_oid,
        "serial_number": record.serial_number,
        "generation_time": _timestamp(record.generation_time),
        "validation_status": record.validation_status,
        # Chemins prévus dans l'archive du passeport de preuve (phase 4).
        "token": {"path": f"timestamp/{record.id}.tsr", "sha256": item.token_sha256},
        "request": {"path": f"timestamp/{record.id}.tsq", "sha256": item.request_sha256},
    }


def _sort_key(item: ManifestTimestamp):
    record = item.record
    return (
        record.purpose != TimestampPurpose.FILE.value,  # FILE d'abord, puis les ancrages
        record.anchored_sequence_number or 0,
        record.generation_time,
        str(record.id),
    )


def _timestamp_status(
    evidence_status: EvidenceStatus,
    timestamps: list[ManifestTimestamp],
    events: list[CustodyEvent],
) -> dict[str, Any]:
    """État explicite de l'horodatage : un tiers voit d'emblée ce qui est garanti."""
    file_valid = any(t.record.purpose == TimestampPurpose.FILE.value for t in timestamps)
    if file_valid:
        file_status = "VALID"
    elif evidence_status is EvidenceStatus.TIMESTAMP_PENDING:
        file_status = "PENDING"
    else:
        file_status = "NONE"
    anchored = max(
        (
            t.record.anchored_sequence_number
            for t in timestamps
            if t.record.purpose == TimestampPurpose.CHAIN_HEAD.value
        ),
        default=None,
    )
    return {
        "file": file_status,
        "chain_head": "ANCHORED" if anchored is not None else "NONE",
        "anchored_sequence_number": anchored,
        # Événements postérieurs au dernier ancrage : couverts par la chaîne seulement,
        # pas encore par un horodatage externe (dont l'événement CHAIN_ANCHORED lui-même).
        "unanchored_events": len(events) - (anchored or 0),
    }


def build_manifest(
    view: EvidenceView,
    events: list[CustodyEvent],
    timestamps: Sequence[ManifestTimestamp] = (),
) -> Manifest:
    evidence = view.evidence
    if EvidenceStatus(evidence.status) not in EXPORTABLE_STATUSES:
        raise EvidenceNotExportableError(f"État {evidence.status} : aucun manifeste possible.")
    document = manifest_crypto.seal(
        {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "evidence": {
                "id": str(evidence.id),
                "organization_id": str(evidence.organization_id),
                "owner_id": str(evidence.owner_id),
                "title": evidence.title,
                "status": evidence.status,
                "created_at": _timestamp(evidence.created_at),
            },
            "files": _file_section(view),
            "custody": _custody_section(events),
            "timestamps": [_timestamp_entry(t) for t in sorted(timestamps, key=_sort_key)],
            "timestamp_status": _timestamp_status(
                EvidenceStatus(evidence.status), list(timestamps), events
            ),
            "tools": {
                "veritas_server": __version__,
                "hash_engine": ENGINE_VERSION,
                "hash_encoding": ENCODING,
                "rfc3161_client": version("rfc3161-client"),
            },
        }
    )
    return Manifest(document=document, content=manifest_crypto.to_bytes(document))
