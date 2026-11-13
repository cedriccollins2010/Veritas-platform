# ADR-0013 — Bibliothèque de vérification `veritas-verifier` (Apache 2.0)

Date : 2026-11-13 · Statut : accepté · Issue : #33

## Contexte

Le document de référence fait du vérificateur autonome la référence de toute vérification : le serveur doit appeler **la même bibliothèque**, et cette bibliothèque est publiée en code ouvert (Apache 2.0), alors que le serveur reste fermé. Jusqu'ici, le code cryptographique pur vivait dans `backend/app/crypto/`. Il ne dépendait d'aucun autre module, mais il faisait partie du serveur : on ne pouvait ni l'installer seul, ni le publier sans publier le serveur.

## Décisions

1. **Un paquet Python distinct, `veritas-verifier`** (module `veritas_verifier`), dans le dossier `verifier/` du dépôt, avec ses propres `pyproject.toml`, `LICENSE` (Apache 2.0), `NOTICE`, `README.md` et tests. Disposition `src/` : les tests s'exécutent contre le paquet installé, pas contre les fichiers du dépôt, ce qui révèle un fichier oublié dans le paquet.
2. **Déplacement sans changement de comportement.** Ces modules passent de `app/crypto/` à `veritas_verifier/` :
   - `canonical`
   - `hash_service`
   - `custody_chain`
   - `manifest`
   - `timestamp_verification`

   Leurs tests purs les suivent (`test_hash_service`, `test_custody_chain`, l'empreinte du manifeste). `app/crypto/` est **supprimé** plutôt que gardé comme simple renvoi : un seul chemin d'import évite qu'une partie du serveur utilise une copie différente. Les ADR précédentes, qui citent `app/crypto/…`, se lisent avec cette correspondance.
3. **Même dépôt plutôt que dépôt public séparé, pour l'instant.** Pour une seule développeuse, deux dépôts à synchroniser sont une source d'écarts : un correctif fait d'un côté, oublié de l'autre. Or le serveur et le vérificateur doivent exécuter exactement le même code. La publication se fera en extrayant le dossier et son historique (`git subtree split --prefix verifier`), sans réécriture.
4. **Dépendances minimales, vérifiées par des tests.** Le paquet n'utilise que la bibliothèque standard, `cryptography`, `rfc3161-client` et `rfc8785`. `tests/test_package.py` analyse chaque import du code source et charge le paquet dans un interpréteur isolé : aucun module du serveur (`app`), ni FastAPI, SQLAlchemy, psycopg, httpx, boto3 ou pydantic. La CI l'installe dans un environnement vierge, comme un tiers.
5. **Bornes de versions plutôt que versions figées** dans le paquet : c'est une bibliothèque, que des tiers installeront à côté d'autres. Les bornes basses sont les versions testées. `rfc3161-client` est borné à `< 1.1`, parce que `timestamp_verification` relit la requête avec une fonction interne de cette bibliothèque. Le serveur continue de figer les versions exactes dans `backend/requirements.txt`.
6. **Installation par le serveur.** Le serveur installe le paquet par `../verifier` dans `backend/requirements.txt` (chemin relatif au dossier `backend/`). En développement, on ajoute `pip install -e ../verifier` pour qu'une modification soit prise en compte sans réinstaller : pip refuse la même bibliothèque deux fois dans un fichier de dépendances. Dans l'image Docker, le paquet est copié dans `/verifier`, à côté de `/app`, grâce au contexte supplémentaire `verifier` de Docker Compose (`additional_contexts`). Le contexte de construction du serveur reste `backend/`, avec son `.dockerignore`.
7. **Les racines de confiance restent côté serveur** (`app/timestamp/trust/`) dans cette étape. Les fonctions les reçoivent en argument et restent pures. Le vérificateur autonome embarquera les siennes (#36).

## Conséquences

- Un tiers peut installer `veritas-verifier` seul (`pip install ./verifier`) et refaire les calculs d'empreinte, de chaîne, de manifeste et de jeton, sans aucune ligne du serveur.
- La CI a un troisième travail, `verifier`. Ruff et pre-commit couvrent `verifier/`.
- `docker build ./backend` seul ne suffit plus : il faut le contexte supplémentaire (`docker build --build-context verifier=./verifier ./backend`) ou passer par Docker Compose.
- Dependabot ne surveille pas `verifier/` : les versions exactes restent suivies dans `backend/requirements.txt`. Relever une borne basse du paquet est une décision volontaire.
