"""Racines de confiance des autorités d'horodatage (dossier app/timestamp/trust/).

Les racines sont des fichiers PEM versionnés dans le dépôt, avec leur provenance
documentée dans trust/README.md : on ne fait confiance qu'à ce qui a été relu.
"""

from functools import cache
from pathlib import Path

from cryptography import x509

TRUST_DIR = Path(__file__).parent / "trust"


@cache
def load_trust_roots() -> tuple[x509.Certificate, ...]:
    """Toutes les racines du dossier trust/ (fichiers *.pem)."""
    roots = []
    for path in sorted(TRUST_DIR.glob("*.pem")):
        roots.extend(x509.load_pem_x509_certificates(path.read_bytes()))
    return tuple(roots)


def get_trust_roots() -> tuple[x509.Certificate, ...]:
    """Dépendance FastAPI (remplacée dans les tests par la racine de la TSA de test)."""
    return load_trust_roots()
