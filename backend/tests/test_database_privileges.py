"""Droits du rôle applicatif veritas_app (migration 0002).

Le tableau EXPECTED_PRIVILEGES est la référence : toute table présente en base doit y
figurer, avec exactement ces droits. Une nouvelle table sans droits explicites, ou un
droit accordé par erreur (UPDATE sur custody_events, TRUNCATE...), fait échouer le test.
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.integration

APP_ROLE = "veritas_app"
ALL_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

READ_WRITE = {"SELECT", "INSERT", "UPDATE"}
APPEND_ONLY = {"SELECT", "INSERT"}

EXPECTED_PRIVILEGES: dict[str, set[str]] = {
    "users": READ_WRITE,
    "organizations": READ_WRITE,
    "organization_members": READ_WRITE | {"DELETE"},
    "sessions": READ_WRITE | {"DELETE"},
    "evidence": READ_WRITE,
    "timestamp_records": READ_WRITE,
    "evidence_files": APPEND_ONLY,
    "hash_records": APPEND_ONLY,
    "custody_events": APPEND_ONLY,
    "verification_records": APPEND_ONLY,
    "access_logs": APPEND_ONLY,
    "alembic_version": set(),
}


def _granted(connection, table: str) -> set[str]:
    return {
        privilege
        for privilege in ALL_PRIVILEGES
        if connection.execute(
            text("SELECT has_table_privilege(:role, :table, :privilege)"),
            {"role": APP_ROLE, "table": f"public.{table}", "privilege": privilege},
        ).scalar_one()
    }


def test_every_table_has_declared_privileges(owner_engine) -> None:
    tables = set(inspect(owner_engine).get_table_names())
    assert tables == set(EXPECTED_PRIVILEGES), "déclarer les droits de chaque nouvelle table"


@pytest.mark.parametrize("table", sorted(EXPECTED_PRIVILEGES))
def test_app_role_privileges(owner_engine, table: str) -> None:
    with owner_engine.connect() as connection:
        assert _granted(connection, table) == EXPECTED_PRIVILEGES[table]


def test_api_account_is_an_unprivileged_member_of_app_role(app_engine) -> None:
    """Le compte de DATABASE_URL n'est ni superutilisateur, ni propriétaire des tables,
    et tient ses droits de veritas_app. Échoue si l'API se connecte en propriétaire."""
    with app_engine.connect() as connection:
        account = connection.execute(
            text(
                "SELECT rolname, rolsuper, rolcreaterole, rolbypassrls, "
                "pg_has_role(rolname, :role, 'USAGE') AS is_member "
                "FROM pg_roles WHERE rolname = current_user"
            ),
            {"role": APP_ROLE},
        ).one()
        owned_tables = connection.execute(
            text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = :u"),
            {"u": account.rolname},
        ).scalar_one()

    assert not account.rolsuper
    assert not account.rolcreaterole
    assert not account.rolbypassrls
    assert account.is_member
    assert owned_tables == 0


def test_api_account_cannot_disable_the_append_only_trigger(app_engine) -> None:
    with app_engine.connect() as connection, connection.begin():
        with pytest.raises(ProgrammingError, match="must be owner"):
            connection.execute(text("ALTER TABLE custody_events DISABLE TRIGGER ALL"))
