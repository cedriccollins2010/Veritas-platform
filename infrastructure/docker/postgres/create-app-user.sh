#!/usr/bin/env bash
# Crée (ou met à jour) le compte de connexion de l'API et le rend membre de veritas_app.
#
# Exécuté automatiquement par l'image postgres au premier démarrage d'un volume vide
# (monté dans /docker-entrypoint-initdb.d), et par la CI. Idempotent : on peut le
# relancer, il resynchronise seulement le mot de passe.
#
# Variables : APP_DB_USER (défaut veritas_app_user), APP_DB_PASSWORD (obligatoire).
# Connexion : variables PG* standard, sinon POSTGRES_USER / POSTGRES_DB (image Docker).
set -euo pipefail

: "${APP_DB_PASSWORD:?définir APP_DB_PASSWORD}"
APP_DB_USER="${APP_DB_USER:-veritas_app_user}"

psql -v ON_ERROR_STOP=1 \
    --username "${PGUSER:-$POSTGRES_USER}" \
    --dbname "${PGDATABASE:-$POSTGRES_DB}" \
    -v app_user="$APP_DB_USER" \
    -v app_password="$APP_DB_PASSWORD" <<'SQL'
-- Rôle de groupe : normalement créé par la migration 0002, mais le script peut passer
-- avant elle (premier démarrage Docker). La migration ne le recrée pas s'il existe.
SELECT 'CREATE ROLE veritas_app NOLOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'veritas_app') \gexec

SELECT format('CREATE ROLE %I LOGIN', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec

-- Un nouveau rôle est déjà NOSUPERUSER, NOCREATEDB, NOCREATEROLE ; un compte non
-- superutilisateur n'a pas le droit de l'écrire explicitement. Le test
-- test_api_account_is_an_unprivileged_member_of_app_role le vérifie.
SELECT format('ALTER ROLE %I LOGIN INHERIT PASSWORD %L', :'app_user', :'app_password') \gexec
SELECT format('GRANT veritas_app TO %I', :'app_user') \gexec
SQL

echo "Compte applicatif « $APP_DB_USER » prêt (membre de veritas_app)."
