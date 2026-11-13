# veritas-verifier

Bibliothèque de vérification des dossiers de preuve **VERITAS**, publiée sous licence Apache 2.0.

VERITAS transforme un fichier en dossier de preuve numérique. Le dossier contient une empreinte SHA-256, un horodatage RFC 3161 émis par une autorité externe, une chaîne de possession et un manifeste. Cette bibliothèque contient **tout le code qui sert à vérifier ces éléments**. Le serveur VERITAS l'utilise tel quel, et un tiers peut l'installer seul pour refaire chaque contrôle sans faire confiance au serveur.

## Contenu

| Module | Rôle |
| --- | --- |
| `hash_service` | Empreinte SHA-256 en flux, comparaison à temps constant |
| `canonical` | Canonicalisation JSON RFC 8785 (JCS), sans nombre à virgule |
| `custody_chain` | Format `veritas-custody-v1` : `H(n) = SHA-256(H(n-1) ‖ JCS(E(n)))`, `verify_chain`, `verify_anchor` |
| `manifest` | Empreinte du manifeste (`manifest_digest`) |
| `timestamp_verification` | Vérification complète d'un jeton RFC 3161 : un résultat par contrôle, `UNKNOWN` pour la révocation hors ligne |

Toutes les fonctions sont **pures** : elles n'utilisent ni base de données, ni réseau, ni horloge système. Les racines de confiance sont passées en argument, jamais lues dans le dossier vérifié.

La commande `veritas verify` et la spécification du passeport de preuve arrivent dans les prochaines versions (issues #34 et #36).

## Installation et tests

```bash
cd verifier
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
ruff check . && ruff format --check .
```

Dépendances : `cryptography`, `rfc3161-client` (>= 1.0.9, la CVE-2025-52556 touche les versions <= 1.0.2) et `rfc8785`. Le paquet ne dépend jamais du serveur VERITAS, et `tests/test_package.py` le vérifie.

## Ce qu'un dossier VERITAS ne prouve pas

Un dossier vérifié montre que le fichier existait **au plus tard** à la date de l'horodatage, et qu'il n'a pas changé depuis. Il ne prouve ni que le contenu dit vrai, ni l'identité de son auteur, ni sa date de création, ni sa recevabilité devant un tribunal.

## Licence

Apache License 2.0 : voir `LICENSE` et `NOTICE`. Seul ce dossier est sous licence ouverte ; le serveur VERITAS ne l'est pas.
