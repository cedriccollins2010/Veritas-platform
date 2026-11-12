"""Rôle applicatif à privilèges minimaux

Correction n° 5 du document de référence : le rôle PostgreSQL avec lequel l'API se
connecte n'a ni UPDATE ni DELETE sur custody_events. Plus largement, l'API ne reçoit
que les droits dont elle a besoin, table par table.

Deux identités distinctes :
- le propriétaire des tables (celui qui lance « alembic upgrade ») peut tout faire,
  y compris désactiver le déclencheur append-only ; il n'est utilisé que pour migrer ;
- veritas_app, rôle de groupe SANS connexion, porte les droits de l'API. Le compte
  de connexion réel (veritas_app_user, mot de passe hors du dépôt) en est membre ;
  il est créé par infrastructure/docker/postgres/create-app-user.sh, jamais par une migration.

Le compte propriétaire doit avoir l'attribut CREATEROLE (ou être superutilisateur)
si veritas_app n'existe pas encore.

Toute nouvelle table doit recevoir ses droits dans la migration qui la crée ;
tests/test_database_privileges.py échoue sinon.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_SQL = r"""
-- Les rôles appartiennent au serveur PostgreSQL entier, pas à une base : il peut donc
-- déjà exister (créé par le script Docker, ou par une montée précédente).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'veritas_app') THEN
        CREATE ROLE veritas_app NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO veritas_app;

-- Lecture et création partout ; aucun TRUNCATE nulle part.
-- UPDATE seulement là où une ligne évolue légitimement :
GRANT SELECT, INSERT, UPDATE ON users TO veritas_app;              -- profil, désactivation
GRANT SELECT, INSERT, UPDATE ON organizations TO veritas_app;      -- renommage
GRANT SELECT, INSERT, UPDATE, DELETE ON organization_members TO veritas_app;  -- retrait
GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO veritas_app;   -- révocation, purge
GRANT SELECT, INSERT, UPDATE ON evidence TO veritas_app;           -- changement d'état
GRANT SELECT, INSERT, UPDATE ON timestamp_records TO veritas_app;  -- résultat de validation

-- Écrits une fois, jamais modifiés :
GRANT SELECT, INSERT ON evidence_files TO veritas_app;
GRANT SELECT, INSERT ON hash_records TO veritas_app;        -- une empreinte n'est jamais écrasée
GRANT SELECT, INSERT ON custody_events TO veritas_app;      -- journal append-only
GRANT SELECT, INSERT ON verification_records TO veritas_app;
GRANT SELECT, INSERT ON access_logs TO veritas_app;         -- journal d'audit

-- alembic_version : aucun droit, l'API n'a pas à connaître ni modifier la version.
"""

DOWNGRADE_SQL = r"""
REVOKE ALL ON
    users, organizations, organization_members, sessions, evidence, evidence_files,
    hash_records, timestamp_records, custody_events, verification_records, access_logs
FROM veritas_app;
REVOKE USAGE ON SCHEMA public FROM veritas_app;
-- Le rôle lui-même est conservé : il appartient au serveur, d'autres comptes de
-- connexion en sont membres, et le supprimer leur retirerait cette appartenance.
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
