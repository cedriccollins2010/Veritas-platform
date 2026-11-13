"""Autorité d'horodatage de test, créée localement avec OpenSSL.

Une racine de test et un certificat de TSA (usage id-kp-timeStamping) ; « reply »
répond à une vraie requête RFC 3161 par un vrai jeton signé. Aucune TSA réelle n'est
appelée, et aucun certificat n'est versionné : tout est généré dans un dossier
temporaire à chaque session de tests.
"""

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509

OPENSSL = shutil.which("openssl")


def run_openssl(*args: str, cwd: Path) -> bytes:
    return subprocess.run(  # noqa: S603 - openssl, arguments contrôlés par le test
        [OPENSSL, *args], cwd=cwd, check=True, capture_output=True
    ).stdout


@dataclass
class LocalTsa:
    directory: Path

    @property
    def ca(self) -> Path:
        return self.directory / "ca.pem"

    @property
    def certificate(self) -> Path:
        return self.directory / "tsa.pem"

    def root(self) -> x509.Certificate:
        return x509.load_pem_x509_certificate(self.ca.read_bytes())

    def reply(self, request: bytes) -> bytes:
        query = self.directory / f"q-{time.monotonic_ns()}.tsq"
        query.write_bytes(request)
        return run_openssl(
            "ts", "-reply", "-config", "ts.cnf", "-queryfile", str(query), cwd=self.directory
        )

    def openssl_verdict(self, response: bytes, request: bytes) -> bool:
        """Verdict d'« openssl ts -verify » avec la requête (empreinte et nonce) et la
        racine de cette TSA comme seule autorité de confiance."""
        stamp = time.monotonic_ns()
        token = self.directory / f"r-{stamp}.tsr"
        query = self.directory / f"v-{stamp}.tsq"
        token.write_bytes(response)
        query.write_bytes(request)
        result = subprocess.run(  # noqa: S603
            [
                OPENSSL,
                "ts",
                "-verify",
                "-queryfile",
                str(query),
                "-in",
                str(token),
                "-CAfile",
                str(self.ca),
            ],
            cwd=self.directory,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and "Verification: OK" in result.stdout

    def verify_with_openssl(self, response: bytes, digest: str) -> bool:
        token = self.directory / f"d-{time.monotonic_ns()}.tsr"
        token.write_bytes(response)
        result = subprocess.run(  # noqa: S603
            [
                OPENSSL,
                "ts",
                "-verify",
                "-digest",
                digest,
                "-in",
                str(token),
                "-CAfile",
                str(self.ca),
                "-untrusted",
                str(self.certificate),
            ],
            cwd=self.directory,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and "Verification: OK" in result.stdout


def create_local_tsa(directory: Path, name: str = "VERITAS Test") -> LocalTsa:
    d = directory
    ec = ["-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes"]
    run_openssl(
        "req",
        "-x509",
        *ec,
        "-keyout",
        "ca.key",
        "-out",
        "ca.pem",
        "-days",
        "2",
        "-subj",
        f"/CN={name} Root CA",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        cwd=d,
    )
    run_openssl(
        "req", *ec, "-keyout", "tsa.key", "-out", "tsa.csr", "-subj", f"/CN={name} TSA", cwd=d
    )
    (d / "ext.cnf").write_text(
        "basicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature\n"
        "extendedKeyUsage=critical,timeStamping\n"
    )
    run_openssl(
        "x509",
        "-req",
        "-in",
        "tsa.csr",
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca.key",
        "-CAcreateserial",
        "-out",
        "tsa.pem",
        "-days",
        "2",
        "-extfile",
        "ext.cnf",
        cwd=d,
    )
    (d / "serial").write_text("01\n")
    (d / "ts.cnf").write_text(
        "[ tsa ]\ndefault_tsa = tsa_config\n[ tsa_config ]\n"
        f"dir = {d}\nserial = $dir/serial\ncrypto_device = builtin\n"
        # Seul le certificat de signature est joint (« certs » omis) : avec plusieurs
        # certificats, OpenSSL ne les trie pas comme l'exige DER, et rfc3161-client,
        # volontairement strict, refuse la réponse.
        "signer_cert = $dir/tsa.pem\nsigner_key = $dir/tsa.key\n"
        "signer_digest = sha256\ndefault_policy = 1.2.3.4.1\ndigests = sha256\n"
        "accuracy = secs:1\nordering = no\ntsa_name = yes\n"
        "ess_cert_id_chain = no\ness_cert_id_alg = sha256\n"
    )
    return LocalTsa(d)
