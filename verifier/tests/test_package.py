"""Le paquet reste indépendant du serveur VERITAS (issue #33).

Un tiers doit pouvoir installer veritas-verifier seul : aucune dépendance vers le code
du serveur (fermé), vers une base de données, un framework web ou un client réseau.
"""

import ast
import importlib.metadata
import subprocess
import sys
from pathlib import Path

import veritas_verifier

PACKAGE_DIR = Path(veritas_verifier.__file__).resolve().parent
# Seules dépendances autorisées, en plus de la bibliothèque standard (voir pyproject.toml).
ALLOWED = {"veritas_verifier", "cryptography", "rfc3161_client", "rfc8785"}
# Modules du serveur qui ne doivent jamais être chargés, même indirectement.
FORBIDDEN = {"app", "fastapi", "starlette", "sqlalchemy", "psycopg", "httpx", "boto3", "pydantic"}


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_every_import_is_stdlib_or_an_allowed_dependency() -> None:
    """Analyse du code source : couvre aussi les imports placés dans une fonction."""
    sources = sorted(PACKAGE_DIR.rglob("*.py"))
    assert sources, "aucun module trouvé"
    for source in sources:
        unexpected = _imported_top_level_modules(source) - ALLOWED - sys.stdlib_module_names
        assert not unexpected, f"{source.name} importe {sorted(unexpected)}"


def test_importing_the_package_loads_no_server_module() -> None:
    """Chargement réel, dans un interpréteur isolé (-I : ni répertoire courant ni PYTHONPATH)."""
    modules = sorted(p.stem for p in PACKAGE_DIR.glob("*.py") if p.stem != "__init__")
    code = (
        "import sys\n"
        + "".join(f"import veritas_verifier.{name}\n" for name in modules)
        + "print(' '.join(sorted({m.split('.')[0] for m in sys.modules})))"
    )
    result = subprocess.run(  # noqa: S603 — interpréteur courant, code écrit ci-dessus
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )
    loaded = set(result.stdout.split())
    assert "veritas_verifier" in loaded
    assert not loaded & FORBIDDEN, sorted(loaded & FORBIDDEN)


def test_version_matches_the_installed_distribution() -> None:
    """La version affichée par le vérificateur est celle du paquet installé."""
    assert veritas_verifier.__version__ == importlib.metadata.version("veritas-verifier")
