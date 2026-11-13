"""Construction du manifeste JSON d'un dossier de preuve (format « veritas-manifest » 1.0).

Le manifeste décrit tout ce qu'un tiers doit vérifier : la preuve, ses fichiers et leurs
empreintes (avec leur origine), la chaîne de possession complète et sa tête, et les
versions des outils. Son schéma est publié dans documentation/api/manifest-v1.schema.json.

Règle : le manifeste est une fonction de l'état enregistré, et de lui seul. Il ne contient
ni date de génération ni valeur aléatoire : deux exports du même dossier sont identiques
octet pour octet. created_at des événements (non haché) n'y figure pas.
"""

from dataclasses import dataclass
from typing import Any

from app import __version__
from app.crypto import canonical, custody_chain
from app.crypto import manifest as manifest_crypto
from app.crypto.hash_service import ENCODING, ENGINE_VERSION
from app.custody.models import CustodyEvent
from app.evidence.models import EvidenceStatus, HashSource
from app.evidence.service import EvidenceView

FORMAT = "veritas-manifest"
FORMAT_VERSION = "1.0"

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


def build_manifest(view: EvidenceView, events: list[CustodyEvent]) -> Manifest:
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
            # Jetons d'horodatage RFC 3161 : ajoutés en phase 3.
            "timestamps": [],
            "tools": {
                "veritas_server": __version__,
                "hash_engine": ENGINE_VERSION,
                "hash_encoding": ENCODING,
            },
        }
    )
    return Manifest(document=document, content=manifest_crypto.to_bytes(document))
