# ADR-0002 — Deux rôles PostgreSQL : propriétaire et application

Date : 2026-11-12 · Statut : accepté

## Contexte

La correction n° 5 du document de référence exige que le rôle PostgreSQL de l'application n'ait ni `UPDATE` ni `DELETE` sur `custody_events`. Jusqu'ici, l'API se connectait avec le propriétaire des tables (`veritas_user`). Le déclencheur append-only bloquait déjà les modifications, mais le propriétaire peut le désactiver avec `ALTER TABLE ... DISABLE TRIGGER`. Une faille dans l'API (injection SQL, exécution de code) aurait donc suffi à réécrire l'historique.

## Décisions

1. **Deux identités.** `veritas_user` possède les tables et ne sert qu'aux migrations (`MIGRATION_DATABASE_URL`). L'API se connecte avec `veritas_app_user` (`DATABASE_URL`), qui n'est propriétaire de rien.
2. **Les droits sont portés par un rôle de groupe, `veritas_app`, sans connexion.** La migration 0002 le crée et lui accorde ses droits table par table : les droits font partie du schéma et sont versionnés avec lui. Le compte de connexion en est seulement membre.
3. **Le compte de connexion est créé hors des migrations**, par `infrastructure/docker/postgres/create-app-user.sh`, parce qu'il a un mot de passe et qu'aucun secret n'entre dans le dépôt. Le même script sert à Docker Compose (premier démarrage du volume) et à la CI.
4. **Privilèges minimaux.** Aucun `TRUNCATE`. `UPDATE` seulement sur les tables dont les lignes évoluent (`users`, `organizations`, `organization_members`, `sessions`, `evidence`, `timestamp_records`). `DELETE` seulement sur `sessions` (purge) et `organization_members` (retrait d'un membre). Les tables d'historique (`custody_events`, `hash_records`, `evidence_files`, `verification_records`, `access_logs`) sont en lecture et ajout seuls. Aucun droit sur `alembic_version`.
5. **Docker Compose sépare les conteneurs.** Un service ponctuel `migrate` applique les migrations avec le compte propriétaire ; le conteneur `backend` ne reçoit que `DATABASE_URL`. Le mot de passe propriétaire n'est jamais dans l'environnement de l'API.
6. **Le downgrade retire les droits mais garde le rôle.** Un rôle appartient au serveur PostgreSQL entier, pas à une base, et des comptes en sont membres ; le supprimer casserait ces appartenances.

## Conséquences

- La protection de `custody_events` a deux barrières : les droits (le compte de l'API reçoit `permission denied`) et le déclencheur (même le propriétaire est refusé).
- **Toute nouvelle table doit recevoir ses droits dans la migration qui la crée.** `tests/test_database_privileges.py` compare les droits réels à un tableau de référence et échoue sinon. Il échoue aussi si l'API se connecte avec le compte propriétaire.
- Le compte propriétaire doit avoir l'attribut `CREATEROLE` (ou être superutilisateur) lors de la première migration. C'est le cas dans Docker et en CI.
- Une base Docker créée avant ce changement n'a pas de compte applicatif : le script ne s'exécute que sur un volume vide (voir README).
- Cela ne protège toujours pas contre un administrateur du serveur PostgreSQL : c'est le rôle de l'ancrage de la tête de chaîne par la TSA (phase 3).
