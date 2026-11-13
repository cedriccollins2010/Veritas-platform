# VERITAS — instructions pour Claude Code

VERITAS transforme un fichier en **dossier de preuve numérique** qu'un tiers peut vérifier seul : empreinte SHA-256, horodatage RFC 3161 par une autorité externe, chaîne de possession chaînée, manifeste versionné, vérificateur autonome. Premier marché : analystes forensic et réponse aux incidents. Projet mené par une seule personne, de niveau intermédiaire, qui veut **comprendre** ce qu'elle construit.

## Façon de travailler

- Réponds et commente en **français**. Le code (noms de variables, fonctions) reste en anglais.
- Explique chaque décision technique en phrases complètes : le but est que la développeuse comprenne pourquoi, pas seulement quoi.
- Avance par petites étapes vérifiables. Une fonctionnalité = une branche `feature/...`, ses tests, sa migration si besoin.
- Avant d'ajouter une dépendance ou une technologie, justifie-la. Pas de microservices, Kubernetes, blockchain ni modèle d'IA dans le MVP.
- Ne marque jamais une tâche comme terminée si les tests, le lint ou le build échouent.

## Flux de travail Git

- Le travail est suivi par des **issues GitHub** (libellé `phase-2` pour l'étape en cours). Commence chaque session en lisant l'issue concernée (`gh issue view <n>`).
- Une issue = une branche (`feature/<n>-court-nom`, ou `fix/`, `chore/`) = une pull request vers `main`, qui contient `Closes #<n>`. Pas de push direct sur `main`.
- Remplis le modèle de pull request, en particulier « Pourquoi » et « Points de sécurité à relire » : la développeuse relit chaque PR avant de fusionner.
- Deux workflows doivent réussir : `CI` (lint, migrations, tests, build) et `Security` (gitleaks, Semgrep). Un échec Semgrep se corrige dans le code ; une exception (`# nosemgrep`) ne s'ajoute qu'avec une justification écrite à côté.
- pre-commit tourne avant chaque commit (ruff, ESLint, gitleaks, fichiers volumineux). Ne jamais le contourner avec `--no-verify`.
- Dependabot ouvre des PR de mise à jour : vérifier que la CI passe et lire le changelog avant de fusionner, surtout pour `cryptography`, `rfc3161-client`, FastAPI et Next.js.

## Document de référence

La spécification à jour est le **Document de référence unifié** : `documentation/requirements/veritas-reference.md` (export Markdown d'un doc Claude ; modifier le doc puis réexporter, ne pas éditer le fichier à la main). Les quatre documents d'origine sont dans `documentation/sources/` : ils sont **remplacés** par le document unifié en cas de contradiction. Décisions clés :

| Sujet | Décision |
| --- | --- |
| Architecture | Monolithe modulaire FastAPI, un package Python par module |
| Authentification | Cookie de session `HttpOnly` + `Secure` + `SameSite=Lax`, sessions en base (seule l'empreinte SHA-256 du jeton, `sessions.token_hash`). Mots de passe Argon2id (`argon2-cffi`). CSRF : en-tête `X-CSRF-Token` = HMAC du jeton de session, vérifié sur tout `/api/v1` (ADR-0003) |
| Organisations | `organization_id` obligatoire partout ; organisation personnelle créée à l'inscription ; toute requête filtre sur l'organisation |
| Fichiers | Tout type, 500 Mo max (configurable) ; mode « empreinte seule » (`storage_mode = HASH_ONLY`, `hash_records.source = CLIENT`) |
| Empreinte | SHA-256 en flux, `app/crypto/hash_service.py` |
| Horodatage | RFC 3161, TSA externe derrière l'interface `TimestampProvider`. DigiCert (`http://timestamp.digicert.com`) en dev et pilote, FreeTSA pour les tests. Bibliothèque `rfc3161-client` **>= 1.0.3** (CVE-2025-52556 avant), envoi HTTP via `httpx`. Comparer aux verdicts de `openssl ts -verify` dans les tests |
| Chaîne de possession | Format `veritas-custody-v1` (ADR-0005) : `H(n) = SHA-256(H(n-1) ‖ JCS(E(n)))`, 32 octets nuls pour le premier, canonicalisation **RFC 8785** (`rfc8785`, pas `json.dumps(sort_keys=True)`). `occurred_at` est haché, `created_at` ne l'est pas. Verrouiller la preuve (`SELECT ... FOR UPDATE`) avant d'insérer un événement. Vérification : `verify_chain` (pure, `app/crypto/custody_chain.py`) |
| Ancrage | Tête de chaîne horodatée par la TSA à l'export (`timestamp_records.purpose = CHAIN_HEAD`) |
| Vérification | Le vérificateur autonome (CLI `veritas verify`, phase 4) est la référence ; le serveur appelle la même bibliothèque. Un résultat par contrôle ; `VALID` seulement si tout est `PASS` ; `UNKNOWN` quand l'information manque. Jamais de PASS artificiel |
| Erreurs d'accès | Preuve inexistante ou d'une autre organisation → **404** dans les deux cas |
| Code ouvert | Vérificateur + spécification du passeport en Apache 2.0 ; serveur fermé |

Ce que VERITAS ne prouve pas, et que l'interface doit rappeler : la véracité du contenu, l'identité de l'auteur, la date de création (seulement « existait au plus tard à »), la recevabilité juridique.

## Commandes

```bash
# Tout l'environnement (PostgreSQL, API, frontend)
cp .env.example .env            # puis changer POSTGRES_PASSWORD et APP_DB_PASSWORD
docker compose up --build       # API : http://localhost:8000/docs · Frontend : http://localhost:3000

# Backend seul (depuis backend/)
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head            # MIGRATION_DATABASE_URL (propriétaire)
bash ../infrastructure/docker/postgres/create-app-user.sh   # une fois : compte de l'API
uvicorn app.main:app --reload   # DATABASE_URL (compte de l'API)
pytest -q                       # les tests marqués integration sont ignorés si PostgreSQL est absent
ruff check . && ruff format .

# Frontend seul (depuis frontend/)
npm install
npm run dev
npm run lint && npm run typecheck && npm run build
```

## Structure

```text
backend/app/
  main.py              création de l'app, CORS, /health
  core/config.py       configuration (pydantic-settings, variables d'environnement)
  database/            moteur SQLAlchemy, get_db, Base
  api/v1/              routes HTTP (préfixe /api/v1) — aucune logique métier ici
  auth/ organizations/ evidence/ storage/ crypto/ timestamp/
  custody/ verification/ reports/ audit/      un module = une responsabilité
backend/migrations/    Alembic ; 0001 = schéma initial complet
backend/tests/
frontend/src/app/      App Router Next.js
frontend/src/services/ appels à l'API
frontend/src/components/
documentation/         spécifications et sources
```

Règles entre modules : les routes appellent des services ; `crypto` ne dépend d'aucun autre module (il sera partagé avec le vérificateur) ; `evidence` n'implémente aucun algorithme cryptographique ; `timestamp` ne gère aucun utilisateur.

## Base de données

- Modèles ORM : `app/<module>/models.py`, réunis par `app/database/models.py` (`target_metadata` d'Alembic). Ils correspondent exactement au schéma migré ; `tests/test_orm_schema.py` et `alembic check` (CI) le vérifient. Toute modification de schéma touche **les deux** : migration et modèle.
- Les migrations restent écrites en SQL et relues à la main. `alembic revision --autogenerate` peut servir de brouillon, mais il ne voit ni les déclencheurs, ni les fonctions, ni le contenu des `CHECK`.
- Valeurs énumérées : `StrEnum` Python + `CHECK ... IN (...)` construit par `sql_in()` ; pas de type `ENUM` PostgreSQL. Les noms de contraintes suivent la convention de PostgreSQL (`NAMING_CONVENTION` dans `database/base.py`).
- `custody_events` : en plus du déclencheur, l'ORM lève `AppendOnlyViolation` sur toute modification ou suppression.
- `custody_events` est append-only : un déclencheur refuse `UPDATE`, `DELETE` et `TRUNCATE`, et le compte de l'API n'a pas ces droits. Ne jamais contourner ce déclencheur ; une correction s'enregistre comme un nouvel événement.
- **Deux comptes PostgreSQL** (ADR-0002) : `veritas_user` possède les tables et ne sert qu'aux migrations (`MIGRATION_DATABASE_URL`) ; l'API utilise `veritas_app_user` (`DATABASE_URL`), membre du rôle `veritas_app`. Ne jamais donner le compte propriétaire à l'API.
- **Toute nouvelle table reçoit ses droits** (`GRANT ... TO veritas_app`) dans la migration qui la crée, et une ligne dans `EXPECTED_PRIVILEGES` de `tests/test_database_privileges.py`. Jamais de `TRUNCATE`, et `UPDATE`/`DELETE` seulement si c'est justifié.
- Pas de suppression en cascade. Identifiants UUID, dates `TIMESTAMPTZ` en UTC.
- Toute nouvelle migration doit passer le cycle `upgrade head → downgrade base → upgrade head` (la CI le vérifie).

## Frontend (Next.js 16)

- Lire `frontend/AGENTS.md` : cette version de Next.js diffère de tes données d'entraînement. Consulter `frontend/node_modules/next/dist/docs/` avant d'écrire du code Next.
- `cacheComponents` est activé : une donnée qui change à chaque requête se lit dans un composant serveur qui appelle `await connection()` (ou une API de requête comme `cookies()`), placé dans un `<Suspense>`. Exemple : `src/components/common/SystemStatus.tsx`.
- Le type global `LayoutProps` est généré : `npm run typecheck` lance `next typegen` avant `tsc`.
- Pas de polices Google ni de ressource tierce chargée par la page.

## Sécurité — non négociable

- Aucun secret dans le dépôt ; `.env` n'est jamais versionné.
- Aucune preuve certifiée n'est modifiée directement.
- Un résultat cryptographique non vérifié n'est jamais affiché comme valide.
- Cryptographie uniquement via des bibliothèques éprouvées, jamais d'implémentation maison.
- Les fichiers déposés ne sont jamais exécutés ni interprétés ; ils sont servis en téléchargement (`Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`).
- Comparer des empreintes avec `hmac.compare_digest` (déjà fait dans `hash_service.digests_match`).
- Ne jamais versionner de vraie pièce à conviction ; utiliser des fichiers de test synthétiques.

## Où en est le projet

- [x] **Sprint 1 — Socle technique** : FastAPI, Next.js, PostgreSQL, Docker Compose, Alembic (schéma complet), `/health` et `/api/v1/health/ready`, page d'état frontend, module SHA-256 testé, CI GitHub Actions.
- [ ] **Phase 2 — Moteur de preuve** (prochaine) : dans l'ordre suggéré
  1. ~~Modèles ORM SQLAlchemy correspondant à la migration 0001.~~ Fait.
     Migration 0002 : rôle applicatif à privilèges minimaux (correction n° 5 du document de référence). Fait.
  2. ~~Authentification minimale~~ Fait (ADR-0003). Routes protégées : dépendances `CurrentUser` / `CurrentOrganization` (`app/auth/dependencies.py`). La garde CSRF s'applique à tout `/api/v1` ; une nouvelle exemption s'ajoute à `CSRF_EXEMPT_PATHS` avec une justification.
  3. ~~Stockage objet~~ Fait (ADR-0004) : `get_storage()` dans `app/storage/` ; clés `new_storage_key()` uniquement ; un fichier n'est jamais réécrit. Pas de serveur S3 dans Docker Compose (MinIO n'est plus distribué) : disque local en dev, S3 géré au pilote.
  4. ~~`POST /api/v1/evidence`~~ Fait (ADR-0005) : réception en flux (`app/evidence/upload.py`), `GET /evidence` et `/evidence/{id}` filtrés sur l'organisation. Format de chaîne `veritas-custody-v1` défini dans `app/crypto/custody_chain.py` ; ajouter un événement : `app.custody.service.append_event`.
  5. Mode empreinte seule.
  6. ~~Chaîne de possession~~ Fait (ADR-0005) : `verify_chain`, `GET /evidence/{id}/events`, tests d'altération et de concurrence. Ne jamais changer les champs hachés sans nouveau numéro de format.
  7. Manifeste JSON v1 et `GET /evidence/{id}/manifest`.
- [ ] Phase 3 — Horodatage et ancrage · Phase 4 — Vérificateur autonome · Phase 5 — MVP professionnel.

Critères d'acceptation du MVP (T01 à T13) : voir le document de référence, section « Plan de réalisation ».
