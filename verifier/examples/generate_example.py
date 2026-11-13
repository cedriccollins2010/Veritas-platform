"""Génère le passeport d'exemple publié avec la spécification (verifier/examples/passport-v1/).

Tout est synthétique : un court texte inventé, une autorité d'horodatage d'exemple créée
pour l'occasion avec OpenSSL, des identifiants fixes. Les clés privées vivent dans un
dossier temporaire supprimé à la fin : seuls le passeport et le certificat racine
d'exemple (public) sont écrits. Relancer le script produit un autre passeport (nouvelles
clés, nouvelles dates), tout aussi valide.

Usage, depuis verifier/ (OpenSSL 3 requis) :
    python examples/generate_example.py
"""

import hashlib
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from cryptography import x509

from veritas_verifier import canonical, custody_chain, passport
from veritas_verifier import manifest as manifest_crypto
from veritas_verifier.hash_service import ENCODING, ENGINE_VERSION
from veritas_verifier.timestamp_verification import verify_timestamp_token

OUTPUT_DIR = Path(__file__).resolve().parent / "passport-v1"
ROOT_FILE = "example-root-ca.pem"
TSA_NAME = "VERITAS Example TSA"
TSA_URL = "http://tsa.example.invalid/"  # domaine réservé : aucune vraie TSA derrière

EVIDENCE_ID = "6f1c3a52-9d0e-4b7a-8c21-5e4f0a9b7d10"
ORGANIZATION_ID = "0b8e2d47-3c15-4f6a-9a72-1d9c8e5b4a01"
OWNER_ID = "a3d5f7e9-1b2c-4d6e-8f01-2a3b4c5d6e70"
FILE_ID = "c4e8a1f2-7b3d-4e5f-9a6b-0c1d2e3f4a50"
FILE_TIMESTAMP_ID = "e1f2a3b4-c5d6-4e7f-8091-a2b3c4d5e6f7"
ANCHOR_TIMESTAMP_ID = "f7e6d5c4-b3a2-4918-8f7e-6d5c4b3a2918"
EVENT_IDS = (
    "11111111-2222-4333-8444-555555555501",
    "11111111-2222-4333-8444-555555555502",
    "11111111-2222-4333-8444-555555555503",
)
ORIGINAL_FILENAME = "note-incident.txt"
ORIGINAL_CONTENT = (
    b"NOTE D'INCIDENT - EXEMPLE SYNTHETIQUE\n"
    b"Ce fichier est invente pour illustrer le format veritas-passport-v1.\n"
    b"Il ne decrit aucun evenement reel.\n"
)


def openssl(*args: str, cwd: Path) -> None:
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603, S607


def create_example_tsa(directory: Path) -> None:
    """Racine et certificat de TSA d'exemple, valables dix ans (pour qu'« openssl ts
    -verify », qui contrôle les dates au moment présent, fonctionne longtemps)."""
    ec = ["-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes"]
    openssl(
        "req", "-x509", *ec, "-keyout", "ca.key", "-out", "ca.pem", "-days", "3650",
        "-subj", "/O=VERITAS example - not trusted/CN=VERITAS Example Root CA",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        cwd=directory,
    )  # fmt: skip
    openssl(
        "req", *ec, "-keyout", "tsa.key", "-out", "tsa.csr",
        "-subj", f"/O=VERITAS example - not trusted/CN={TSA_NAME}",
        cwd=directory,
    )  # fmt: skip
    (directory / "ext.cnf").write_text(
        "basicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature\n"
        "extendedKeyUsage=critical,timeStamping\n"
    )
    openssl(
        "x509", "-req", "-in", "tsa.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
        "-CAcreateserial", "-out", "tsa.pem", "-days", "3650", "-extfile", "ext.cnf",
        cwd=directory,
    )  # fmt: skip
    (directory / "serial").write_text("01\n")
    (directory / "ts.cnf").write_text(
        "[ tsa ]\ndefault_tsa = tsa_config\n[ tsa_config ]\n"
        f"dir = {directory}\nserial = $dir/serial\ncrypto_device = builtin\n"
        "signer_cert = $dir/tsa.pem\nsigner_key = $dir/tsa.key\n"
        "signer_digest = sha256\ndefault_policy = 2.999.1\ndigests = sha256\n"
        "accuracy = secs:1\nordering = no\ntsa_name = yes\n"
        "ess_cert_id_chain = no\ness_cert_id_alg = sha256\n"
    )


def timestamp(directory: Path, digest: str, name: str, root: x509.Certificate):
    """Requête (avec nonce et demande de certificat), réponse, puis vérification."""
    openssl(
        "ts", "-query", "-digest", digest, "-sha256", "-cert", "-out", f"{name}.tsq",
        cwd=directory,
    )  # fmt: skip
    openssl(
        "ts", "-reply", "-config", "ts.cnf", "-queryfile", f"{name}.tsq", "-out", f"{name}.tsr",
        cwd=directory,
    )  # fmt: skip
    request = (directory / f"{name}.tsq").read_bytes()
    response = (directory / f"{name}.tsr").read_bytes()
    verification = verify_timestamp_token(response, request, digest, [root])
    if not verification.valid:
        raise RuntimeError(f"Jeton d'exemple invalide : {verification.checks}")
    return request, response, verification


def now() -> str:
    return custody_chain.format_timestamp(datetime.now(UTC))


def chain_event(sequence: int, previous: str | None, event_type: str, data: dict) -> dict:
    occurred_at = now()
    payload = custody_chain.event_payload(
        event_id=EVENT_IDS[sequence - 1],
        evidence_id=EVIDENCE_ID,
        sequence_number=sequence,
        event_type=event_type,
        actor_id=OWNER_ID,
        occurred_at=occurred_at,
        event_data=data,
    )
    return {
        "event_id": EVENT_IDS[sequence - 1],
        "sequence_number": sequence,
        "event_type": event_type,
        "actor_id": OWNER_ID,
        "occurred_at": occurred_at,
        "event_data": data,
        "previous_event_hash": previous,
        "event_hash": custody_chain.event_hash(previous, payload),
    }


def timestamp_entry(record_id, purpose, imprint, anchored, verification, request, response):
    token_path, request_path = passport.timestamp_paths(record_id)
    return {
        "timestamp_record_id": record_id,
        "purpose": purpose,
        "hash_algorithm": "SHA-256",
        "message_imprint": imprint,
        "anchored_sequence_number": anchored,
        "tsa": {"name": TSA_NAME, "url": TSA_URL},
        "policy_oid": verification.policy_oid,
        "serial_number": verification.serial_number,
        "generation_time": custody_chain.format_timestamp(verification.generation_time),
        "validation_status": "VALID",
        "token": {"path": token_path, "sha256": hashlib.sha256(response).hexdigest()},
        "request": {"path": request_path, "sha256": hashlib.sha256(request).hexdigest()},
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        create_example_tsa(work)
        root = x509.load_pem_x509_certificate((work / "ca.pem").read_bytes())
        digest = hashlib.sha256(ORIGINAL_CONTENT).hexdigest()

        created_at = now()
        received = chain_event(
            1,
            None,
            "FILE_RECEIVED",
            {
                "file_id": FILE_ID,
                "original_filename": ORIGINAL_FILENAME,
                "media_type": "text/plain",
                "size": len(ORIGINAL_CONTENT),
                "hash_algorithm": "SHA-256",
                "digest": digest,
                "storage_mode": "STORED",
                "hash_source": "SERVER",
            },
        )
        file_request, file_response, file_check = timestamp(work, digest, "file", root)
        attached = chain_event(
            2,
            received["event_hash"],
            "TIMESTAMP_ATTACHED",
            {
                "timestamp_record_id": FILE_TIMESTAMP_ID,
                "purpose": "FILE",
                "message_imprint": digest,
                "tsa_name": TSA_NAME,
                "tsa_url": TSA_URL,
                "generation_time": custody_chain.format_timestamp(file_check.generation_time),
                "serial_number": file_check.serial_number,
                "policy_oid": file_check.policy_oid,
                "token_sha256": hashlib.sha256(file_response).hexdigest(),
            },
        )
        head = attached["event_hash"]
        anchor_request, anchor_response, anchor_check = timestamp(work, head, "anchor", root)
        anchored = chain_event(
            3,
            head,
            "CHAIN_ANCHORED",
            {
                "timestamp_record_id": ANCHOR_TIMESTAMP_ID,
                "anchored_sequence_number": 2,
                "anchored_hash": head,
                "tsa_name": TSA_NAME,
                "tsa_url": TSA_URL,
                "generation_time": custody_chain.format_timestamp(anchor_check.generation_time),
                "serial_number": anchor_check.serial_number,
                "token_sha256": hashlib.sha256(anchor_response).hexdigest(),
            },
        )
        events = [received, attached, anchored]

        document = manifest_crypto.seal(
            {
                "format": passport.MANIFEST_FORMAT,
                "format_version": "1.1",
                "evidence": {
                    "id": EVIDENCE_ID,
                    "organization_id": ORGANIZATION_ID,
                    "owner_id": OWNER_ID,
                    "title": "Exemple synthétique - note d'incident",
                    "status": "CERTIFIED",
                    "created_at": created_at,
                },
                "files": [
                    {
                        "id": FILE_ID,
                        "original_filename": ORIGINAL_FILENAME,
                        "media_type": "text/plain",
                        "size": len(ORIGINAL_CONTENT),
                        "storage_mode": "STORED",
                        "hashes": [
                            {
                                "algorithm": "SHA-256",
                                "encoding": ENCODING,
                                "digest": digest,
                                "engine_version": ENGINE_VERSION,
                                "source": "SERVER",
                                "verified_by_server": True,
                                "calculated_at": received["occurred_at"],
                            }
                        ],
                    }
                ],
                "custody": {
                    "format": custody_chain.FORMAT,
                    "canonicalization": canonical.ALGORITHM,
                    "hash_algorithm": "SHA-256",
                    "genesis": custody_chain.GENESIS.hex(),
                    "event_count": len(events),
                    "head_hash": events[-1]["event_hash"],
                    "events": events,
                },
                "timestamps": [
                    timestamp_entry(
                        FILE_TIMESTAMP_ID,
                        "FILE",
                        digest,
                        None,
                        file_check,
                        file_request,
                        file_response,
                    ),
                    timestamp_entry(
                        ANCHOR_TIMESTAMP_ID,
                        "CHAIN_HEAD",
                        head,
                        2,
                        anchor_check,
                        anchor_request,
                        anchor_response,
                    ),
                ],  # fmt: skip
                "timestamp_status": {
                    "file": "VALID",
                    "chain_head": "ANCHORED",
                    "anchored_sequence_number": 2,
                    "unanchored_events": 1,
                },
                "tools": {
                    "veritas_server": "example",
                    "hash_engine": ENGINE_VERSION,
                    "hash_encoding": ENCODING,
                    "rfc3161_client": version("rfc3161-client"),
                },
            }
        )

        file_token, file_query = passport.timestamp_paths(FILE_TIMESTAMP_ID)
        anchor_token, anchor_query = passport.timestamp_paths(ANCHOR_TIMESTAMP_ID)
        entries = {
            passport.MANIFEST_PATH: manifest_crypto.to_bytes(document),
            passport.original_path(FILE_ID): ORIGINAL_CONTENT,
            file_token: file_response,
            file_query: file_request,
            anchor_token: anchor_response,
            anchor_query: anchor_request,
        }
        if OUTPUT_DIR.exists():
            for old in OUTPUT_DIR.glob("*.zip"):
                old.unlink()
        OUTPUT_DIR.mkdir(exist_ok=True)
        archive = OUTPUT_DIR / f"veritas-passport-{EVIDENCE_ID}.zip"
        with archive.open("wb") as destination:
            passport.write_passport(destination, entries)
        shutil.copyfile(work / "ca.pem", OUTPUT_DIR / ROOT_FILE)
    print(f"Écrit : {archive}")
    print(f"Racine d'exemple : {OUTPUT_DIR / ROOT_FILE}")


if __name__ == "__main__":
    main()
