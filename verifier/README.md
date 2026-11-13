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
| `passport` | Archive `veritas-passport-v1` : noms autorisés, entrées attendues, écriture déterministe |
| `schemas/` | Schémas JSON du manifeste (1.0 et 1.1) |

Les fonctions de vérification sont **pures** : elles n'utilisent ni base de données, ni réseau, ni horloge système. Seul `write_passport` écrit, dans le fichier qu'on lui donne. Les racines de confiance sont passées en argument, jamais lues dans le dossier vérifié.

**Spécification :** [`SPECIFICATION.md`](SPECIFICATION.md) décrit le passeport de preuve et chaque contrôle, assez précisément pour écrire un autre vérificateur. Un passeport d'exemple, vérifiable à la main, est dans [`examples/passport-v1/`](examples/passport-v1/README.md). La commande `veritas verify` arrive avec l'issue #36.

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
