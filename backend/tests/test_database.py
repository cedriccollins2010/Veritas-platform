"""Tests d'intégration : nécessitent PostgreSQL avec les migrations appliquées
(alembic upgrade head) et le compte applicatif créé. Ignorés si la base est inaccessible.

Les tests passent par le compte de l'API (DATABASE_URL), sauf mention contraire."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

pytestmark = pytest.mark.integration


def _rolled_back(engine):
    with engine.connect() as conn:
        transaction = conn.begin()
        yield conn
        transaction.rollback()


@pytest.fixture
def connection(app_engine):
    yield from _rolled_back(app_engine)


@pytest.fixture
def owner_connection(owner_engine):
    yield from _rolled_back(owner_engine)


def _create_evidence(conn) -> uuid.UUID:
    user_id = conn.execute(
        text("INSERT INTO users (email, password_hash) VALUES (:e, 'x') RETURNING id"),
        {"e": f"{uuid.uuid4()}@test.local"},
    ).scalar_one()
    org_id = conn.execute(
        text("INSERT INTO organizations (name, is_personal) VALUES ('Test', TRUE) RETURNING id")
    ).scalar_one()
    return conn.execute(
        text(
            "INSERT INTO evidence (organization_id, owner_id, title) "
            "VALUES (:o, :u, 'Dossier test') RETURNING id"
        ),
        {"o": org_id, "u": user_id},
    ).scalar_one()


def _insert_event(conn, evidence_id, sequence, previous, event_hash) -> None:
    conn.execute(
        text(
            "INSERT INTO custody_events (evidence_id, event_type, sequence_number, occurred_at, "
            "previous_event_hash, event_hash) VALUES (:ev, 'FILE_UPLOADED', :s, NOW(), :p, :h)"
        ),
        {"ev": evidence_id, "s": sequence, "p": previous, "h": event_hash},
    )


def test_readiness_reports_database_up(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "up"


def test_evidence_requires_an_organization(connection) -> None:
    with pytest.raises(IntegrityError):
        connection.execute(
            text("INSERT INTO evidence (organization_id, owner_id, title) VALUES (NULL, NULL, 'x')")
        )


def test_api_account_has_no_update_or_delete_on_custody_events(connection) -> None:
    """Première barrière : le compte de l'API n'a tout simplement pas le droit."""
    evidence_id = _create_evidence(connection)
    _insert_event(connection, evidence_id, 1, None, "a" * 64)

    for statement in (
        "UPDATE custody_events SET event_type = 'FALSIFIED'",
        "DELETE FROM custody_events",
        "TRUNCATE custody_events",
    ):
        savepoint = connection.begin_nested()
        with pytest.raises(ProgrammingError, match="permission denied"):
            connection.execute(text(statement))
        savepoint.rollback()


def test_trigger_blocks_even_the_table_owner(owner_connection) -> None:
    """Seconde barrière : le déclencheur refuse aussi le propriétaire des tables."""
    evidence_id = _create_evidence(owner_connection)
    _insert_event(owner_connection, evidence_id, 1, None, "a" * 64)

    for statement in (
        "UPDATE custody_events SET event_type = 'FALSIFIED'",
        "DELETE FROM custody_events",
        "TRUNCATE custody_events",
    ):
        savepoint = owner_connection.begin_nested()
        with pytest.raises(DBAPIError, match="append-only"):
            owner_connection.execute(text(statement))
        savepoint.rollback()


def test_custody_sequence_is_unique_per_evidence(connection) -> None:
    evidence_id = _create_evidence(connection)
    _insert_event(connection, evidence_id, 1, None, "a" * 64)
    with pytest.raises(IntegrityError):
        _insert_event(connection, evidence_id, 1, None, "b" * 64)


def test_only_first_event_has_no_previous_hash(connection) -> None:
    evidence_id = _create_evidence(connection)
    with pytest.raises(IntegrityError):
        _insert_event(connection, evidence_id, 2, None, "c" * 64)
