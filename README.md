# VERITAS

**Trust through verifiable evidence — la confiance par la preuve vérifiable.**

VERITAS constitue des dossiers de preuve numérique qu'un tiers peut vérifier sans faire confiance au serveur qui les a produits : empreinte SHA-256, horodatage RFC 3161 par une autorité externe, chaîne de possession chaînée et vérificateur autonome.

> État : **Sprint 1 terminé** — socle technique opérationnel. Le moteur de preuve arrive en phase 2.

## Démarrage rapide

Prérequis : Docker Desktop (ou Docker Engine avec Compose) et Git.

```bash
git clone <url-du-depot> veritas-platform
cd veritas-platform
cp .env.example .env        # puis remplacer POSTGRES_PASSWORD et APP_DB_PASSWORD
docker compose up --build
```

| Service | Adresse |
| --- | --- |
| Frontend | http://localhost:3000 — affiche l'état de l'API et de la base |
| API | http://localhost:8000 |
| Documentation OpenAPI | http://localhost:8000/docs |
| Disponibilité | http://localhost:8000/api/v1/health/ready |

Arrêt : `docker compose down`. Pour effacer aussi la base locale : `docker compose down -v` (**supprime les données**).

Base créée avant la migration 0002 (compte applicatif absent) : la recréer avec `docker compose down -v`, ou créer le compte dans la base existante :

```bash
docker compose up -d db          # recrée le conteneur avec APP_DB_PASSWORD
docker compose exec db bash /docker-entrypoint-initdb.d/10-create-app-user.sh
docker compose up --build
```

## Développement sans Docker

**Backend** (Python 3.12 ou plus récent), depuis `backend/` :

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell : .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e ../verifier         # bibliothèque de vérification, modifiable sans réinstaller
alembic upgrade head               # compte propriétaire : MIGRATION_DATABASE_URL dans .env
# Une fois : compte de l'API (variables PG* = compte propriétaire, APP_DB_PASSWORD = .env)
bash ../infrastructure/docker/postgres/create-app-user.sh
uvicorn app.main:app --reload      # compte de l'API : DATABASE_URL dans .env
pytest -q
```

Deux comptes PostgreSQL : le propriétaire des tables ne sert qu'aux migrations, l'API se connecte avec un compte aux droits minimaux. Voir `documentation/architecture/ADR-0002-roles-postgresql.md`.

**Bibliothèque de vérification** (`verifier/`, Apache 2.0), testée seule : voir `verifier/README.md`.

**Frontend** (Node.js 22), depuis `frontend/` :

```bash
npm install
npm run dev
```

**Contrôles avant commit** (une fois par poste, depuis la racine) :

```bash
pip install pre-commit
pre-commit install        # ruff, ESLint, gitleaks et contrôles de fichiers à chaque commit
```

## Contribuer

Chaque changement part d'une issue, se fait dans une branche et arrive dans `main` par une pull request dont les workflows `CI` et `Security` doivent réussir. Les mises à jour de dépendances sont proposées par Dependabot.

## Organisation du dépôt

```text
backend/          API FastAPI (monolithe modulaire), migrations Alembic, tests
verifier/         Bibliothèque de vérification veritas-verifier (Apache 2.0), partagée avec le serveur
frontend/         Interface Next.js / React / TypeScript
documentation/    Spécifications, architecture, sécurité, documents sources
infrastructure/   Scripts et configuration Docker supplémentaires
.github/          Intégration continue (lint, migrations, tests, build)
CLAUDE.md         Contexte et règles pour Claude Code
```

## Ce que VERITAS prouve, et ce qu'il ne prouve pas

VERITAS démontre l'**intégrité** d'un fichier, son **existence au plus tard à une date** attestée par une autorité d'horodatage, et la **traçabilité** des opérations sur le dossier. Il ne prouve ni la véracité du contenu, ni l'identité de l'auteur, ni la date de création, ni la recevabilité juridique.
