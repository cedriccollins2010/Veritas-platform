"""Tests d'intégration : nécessitent PostgreSQL avec les migrations appliquées
(alembic upgrade head). Ignorés automatiquement si la base est inaccessible."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def connection():
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        transaction = conn.begin()
        yield conn
        transaction.rollback()
    engine.dispose()


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


def test_custody_events_cannot_be_updated_or_deleted(connection) -> None:
    evidence_id = _create_evidence(connection)
    _insert_event(connection, evidence_id, 1, None, "a" * 64)

    savepoint = connection.begin_nested()
    with pytest.raises(DBAPIError, match="append-only"):
        connection.execute(text("UPDATE custody_events SET event_type = 'FALSIFIED'"))
    savepoint.rollback()

    savepoint = connection.begin_nested()
    with pytest.raises(DBAPIError, match="append-only"):
        connection.execute(text("DELETE FROM custody_events"))
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
