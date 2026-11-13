# ADR-0010 — Horodatage d'une preuve et reprise sur panne

Date : 2026-11-13 · Statut : accepté · Issue : #25

## Contexte

Après le dépôt, chaque preuve doit être horodatée par une TSA externe, et son jeton vérifié, avant d'être déclarée `CERTIFIED`. La TSA peut être lente ou en panne : le fichier et l'empreinte ne doivent jamais être perdus, et l'horodatage doit pouvoir être relancé (T12).

## Décisions

1. **Cycle de vie** : `HASHED` → `TIMESTAMP_PENDING` → `CERTIFIED` seulement avec un jeton vérifié `VALID` (ADR-0009), conservé et rattaché. TSA en panne (injoignable, délai, refus) : la tentative est enregistrée `ERROR`, la preuve reste `TIMESTAMP_PENDING`. Jeton refusé par la vérification : tentative `INVALID`, la preuve reste `TIMESTAMP_PENDING`. Chaque tentative est une ligne de `timestamp_records` et une entrée `evidence.timestamp` dans `access_logs`.
2. **Horodatage du dépôt en tâche de fond** (`BackgroundTasks` de FastAPI) : le dépôt répond immédiatement, l'horodatage s'exécute juste après, dans le même processus, avec sa propre session. Aucune infrastructure de file d'attente. Si le processus s'arrête avant, la preuve reste `HASHED` ou `TIMESTAMP_PENDING`, et la relance la rattrape. Écarté : l'appel pendant la requête (le dépôt attendrait jusqu'à `TSA_TIMEOUT_SECONDS` en cas de TSA lente). Désactivable par `TIMESTAMP_ON_DEPOSIT=false`.
3. **Relance synchrone** : `POST /evidence/{id}/timestamp` (filtré sur l'organisation, jeton CSRF). Réponses : 200 (`CERTIFIED`), 503 (TSA indisponible), 502 (jeton refusé), 409 (déjà certifiée, ou état qui ne permet pas l'horodatage), 404 (inexistante ou autre organisation).
4. **Verrou** : chaque tentative verrouille la preuve (`SELECT ... FOR UPDATE`) jusqu'à sa fin, appel à la TSA compris. Deux tentatives simultanées passent l'une après l'autre, et la seconde constate `CERTIFIED` et s'arrête. La transaction reste donc ouverte pendant l'appel à la TSA, borné par `TSA_TIMEOUT_SECONDS` (10 s) : c'est acceptable au volume du MVP.
5. **Événement `TIMESTAMP_ATTACHED`** ajouté à la chaîne de possession au moment de la certification : identifiant de la tentative, empreinte horodatée, TSA, date de génération, numéro de série, policy OID et **empreinte SHA-256 du fichier `.tsr` conservé** (malléabilité CMS, ADR-0009).
6. **Empreinte seule** : la preuve est horodatée de la même façon. Le jeton atteste que l'empreinte *déclarée* existait à cette date ; `verified_by_server` reste faux.
7. **Les réponses de l'API** indiquent la dernière tentative (`timestamp` : statut, TSA, date de génération, date de la tentative, cause d'un échec). Seul le statut `VALID` signifie un jeton vérifié.

## Conséquences

- Les tests remplacent par défaut la TSA par une TSA « indisponible » (échec immédiat) : aucun test n'attend une TSA réelle. Les tests d'horodatage utilisent la TSA locale OpenSSL.
- La relance automatique périodique des preuves en attente n'est pas faite (hors périmètre) : une tâche planifiée simple pourra appeler la même fonction.
- Un jeton est conservé même s'il est refusé (`INVALID`) : il documente la tentative.
