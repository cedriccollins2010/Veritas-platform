# VERITAS — instructions pour Claude Code

VERITAS transforme un fichier en **dossier de preuve numérique** qu'un tiers peut vérifier seul : empreinte SHA-256, horodatage RFC 3161 par une autorité externe, chaîne de possession chaînée, manifeste versionné, vérificateur autonome. Premier marché : analystes forensic et réponse aux incidents. Projet mené par une seule personne, de niveau intermédiaire, qui veut **comprendre** ce qu'elle construit.

## Façon de travailler

- Réponds et commente en **français**. Le code (noms de variables, fonctions) reste en anglais.
- Explique chaque décision technique en phrases complètes : le but est que la développeuse comprenne pourquoi, pas seulement quoi.
- Avance par petites étapes vérifiables. Une fonctionnalité = une branche `feature/...`, ses tests, sa migration si besoin.
- Avant d'ajouter une dépendance ou une technologie, justifie-la. Pas de microservices, Kubernetes, blockchain ni modèle d'IA dans le MVP.
- Ne marque jamais une tâche comme terminée si les tests, le lint ou le build échouent.

## Document de référence

La spécification à jour est le **Document de référence unifié** (doc Claude, à exporter en Markdown dans `documentation/requirements/`). Les quatre documents d'origine sont dans `documentation/sources/` : ils sont **remplacés** par le document unifié en cas de contradiction. Décisions clés :

| Sujet | Décision |
| --- | --- |
| Architecture | Monolithe modulaire FastAPI, un package Python par module |
| Authentification | Cookie de session `HttpOnly` + `Secure` + `SameSite`, protection CSRF, sessions en base (`sessions.token_hash`). Aucun jeton dans le navigateur |
| Organisations | `organization_id` obligatoire partout ; organisation personnelle créée à l'inscription ; toute requête filtre sur l'organisation |
| Fichiers | Tout type, 500 Mo max (configurable) ; mode « empreinte seule » (`storage_mode = HASH_ONLY`, `hash_records.source = CLIENT`) |
| Empreinte | SHA-256 en flux, `app/crypto/hash_service.py` |
| Horodatage | RFC 3161, TSA externe derrière l'interface `TimestampProvider`. DigiCert (`http://timestamp.digicert.com`) en dev et pilote, FreeTSA pour les tests. Bibliothèque `rfc3161-client` **>= 1.0.3** (CVE-2025-52556 avant), envoi HTTP via `httpx`. Comparer aux verdicts de `openssl ts -verify` dans les tests |
| Chaîne de possession | `H(n) = SHA-256(H(n-1) ‖ JCS(E(n)))`, canonicalisation **RFC 8785** (pas `json.dumps(sort_keys=True)`). `occurred_at` est haché, `created_at` ne l'est pas. Verrouiller la preuve (`SELECT ... FOR UPDATE`) avant d'insérer un événement |
| Ancrage | Tête de chaîne horodatée par la TSA à l'export (`timestamp_records.purpose = CHAIN_HEAD`) |
| Vérification | Le vérificateur autonome (CLI `veritas verify`, phase 4) est la référence ; le serveur appelle la même bibliothèque. Un résultat par contrôle ; `VALID` seulement si tout est `PASS` ; `UNKNOWN` quand l'information manque. Jamais de PASS artificiel |
| Erreurs d'accès | Preuve inexistante ou d'une autre organisation → **404** dans les deux cas |
| Code ouvert | Vérificateur + spécification du passeport en Apache 2.0 ; serveur fermé |

Ce que VERITAS ne prouve pas, et que l'interface doit rappeler : la véracité du contenu, l'identité de l'auteur, la date de création (seulement « existait au plus tard à »), la recevabilité juridique.

## Commandes

```bash
# Tout l'environnement (PostgreSQL, API, frontend)
cp .env.example .env            # puis changer POSTGRES_PASSWORD
docker compose up --build       # API : http://localhost:8000/docs · Frontend : http://localhost:3000

# Backend seul (depuis backend/)
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
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

- Les migrations sont **écrites à la main** en SQL. `target_metadata = None` dans `migrations/env.py` : **ne pas utiliser `alembic revision --autogenerate`** tant que les modèles ORM (phase 2) ne décrivent pas toutes les tables, sinon Alembic proposera de les supprimer.
- Les modèles ORM, quand ils seront écrits, doivent correspondre exactement à la migration 0001.
- `custody_events` est append-only : un déclencheur refuse `UPDATE`, `DELETE` et `TRUNCATE`. Ne jamais contourner ce déclencheur ; une correction s'enregistre comme un nouvel événement.
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
  1. Modèles ORM SQLAlchemy correspondant à la migration 0001.
  2. Authentification minimale : inscription (avec organisation personnelle), connexion, déconnexion, `/auth/me`, cookie de session, CSRF.
  3. Stockage objet : interface `Storage` + implémentation disque local pour le dev, puis S3 (MinIO dans Docker Compose).
  4. `POST /api/v1/evidence` : réception en flux vers un fichier temporaire, limite de taille, SHA-256, stockage, premier événement de possession, état `HASHED`.
  5. Mode empreinte seule.
  6. Canonicalisation RFC 8785 et chaîne de possession, avec tests (modification, suppression, réordonnancement, rupture).
  7. Manifeste JSON v1 et `GET /evidence/{id}/manifest`.
- [ ] Phase 3 — Horodatage et ancrage · Phase 4 — Vérificateur autonome · Phase 5 — MVP professionnel.

Critères d'acceptation du MVP (T01 à T13) : voir le document de référence, section « Plan de réalisation ».
