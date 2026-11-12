# VERITAS

**Trust through verifiable evidence — la confiance par la preuve vérifiable.**

VERITAS constitue des dossiers de preuve numérique qu'un tiers peut vérifier sans faire confiance au serveur qui les a produits : empreinte SHA-256, horodatage RFC 3161 par une autorité externe, chaîne de possession chaînée et vérificateur autonome.

> État : **Sprint 1 terminé** — socle technique opérationnel. Le moteur de preuve arrive en phase 2.

## Démarrage rapide

Prérequis : Docker Desktop (ou Docker Engine avec Compose) et Git.

```bash
git clone <url-du-depot> veritas-platform
cd veritas-platform
cp .env.example .env        # puis remplacer POSTGRES_PASSWORD
docker compose up --build
```

| Service | Adresse |
| --- | --- |
| Frontend | http://localhost:3000 — affiche l'état de l'API et de la base |
| API | http://localhost:8000 |
| Documentation OpenAPI | http://localhost:8000/docs |
| Disponibilité | http://localhost:8000/api/v1/health/ready |

Arrêt : `docker compose down`. Pour effacer aussi la base locale : `docker compose down -v` (**supprime les données**).

## Développement sans Docker

**Backend** (Python 3.12 ou plus récent), depuis `backend/` :

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell : .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head               # nécessite PostgreSQL (DATABASE_URL dans .env)
uvicorn app.main:app --reload
pytest -q
```

**Frontend** (Node.js 22), depuis `frontend/` :

```bash
npm install
npm run dev
```

## Organisation du dépôt

```text
backend/          API FastAPI (monolithe modulaire), migrations Alembic, tests
frontend/         Interface Next.js / React / TypeScript
documentation/    Spécifications, architecture, sécurité, documents sources
infrastructure/   Scripts et configuration Docker supplémentaires
.github/          Intégration continue (lint, migrations, tests, build)
CLAUDE.md         Contexte et règles pour Claude Code
```

## Ce que VERITAS prouve, et ce qu'il ne prouve pas

VERITAS démontre l'**intégrité** d'un fichier, son **existence au plus tard à une date** attestée par une autorité d'horodatage, et la **traçabilité** des opérations sur le dossier. Il ne prouve ni la véracité du contenu, ni l'identité de l'auteur, ni la date de création, ni la recevabilité juridique.
