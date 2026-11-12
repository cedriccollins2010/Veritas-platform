"""Les modèles ORM doivent décrire exactement le schéma créé par les migrations.

Tests d'intégration : nécessitent PostgreSQL avec « alembic upgrade head » appliqué.
"""

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.orm import Session

from app.audit.models import AccessOutcome
from app.custody.models import AppendOnlyViolation
from app.database import models
from app.database.models import Base
from app.evidence.models import EvidenceStatus, HashAlgorithm, HashSource, StorageMode
from app.organizations.models import MemberRole
from app.timestamp.models import (
    TimestampHashAlgorithm,
    TimestampPurpose,
    TimestampValidationStatus,
)
from app.verification.models import (
    CheckResult,
    Completeness,
    OptionalCheckResult,
    OverallStatus,
)

pytestmark = pytest.mark.integration

# Tables gérées par Alembic lui-même, absentes des modèles.
IGNORED_TABLES = {"alembic_version"}


@pytest.fixture(scope="module")
def engine(app_engine):
    return app_engine


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    return not (type_ == "table" and name in IGNORED_TABLES)


def test_models_match_migrated_schema(engine) -> None:
    """Aucune différence de tables, colonnes, types, nullabilité, valeurs par défaut,
    clés étrangères, contraintes d'unicité ni index."""
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "compare_server_default": True,
                "include_object": _include_object,
            },
        )
        differences = compare_metadata(context, Base.metadata)
    assert differences == []


def test_check_constraint_names_match(engine) -> None:
    """compare_metadata ignore les CHECK : on compare leurs noms séparément."""
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        in_models = {c.name for c in table.constraints if isinstance(c, CheckConstraint) and c.name}
        in_database = {c["name"] for c in inspector.get_check_constraints(table.name)}
        assert in_models == in_database, table.name


# Chaque colonne à valeurs énumérées, avec l'énumération Python correspondante.
ENUM_COLUMNS: list[tuple[str, str, type[StrEnum]]] = [
    ("organization_members", "role", MemberRole),
    ("evidence", "status", EvidenceStatus),
    ("evidence_files", "storage_mode", StorageMode),
    ("hash_records", "algorithm", HashAlgorithm),
    ("hash_records", "source", HashSource),
    ("timestamp_records", "purpose", TimestampPurpose),
    ("timestamp_records", "hash_algorithm", TimestampHashAlgorithm),
    ("timestamp_records", "validation_status", TimestampValidationStatus),
    ("verification_records", "manifest_status", CheckResult),
    ("verification_records", "integrity_status", CheckResult),
    ("verification_records", "timestamp_status", OptionalCheckResult),
    ("verification_records", "certificate_status", OptionalCheckResult),
    ("verification_records", "custody_status", CheckResult),
    ("verification_records", "completeness", Completeness),
    ("verification_records", "overall_status", OverallStatus),
    ("access_logs", "outcome", AccessOutcome),
]


def test_enums_match_database_check_values(engine) -> None:
    """Les valeurs des énumérations Python sont exactement celles acceptées en base."""
    inspector = inspect(engine)
    for table, column, enum in ENUM_COLUMNS:
        constraint = next(
            c
            for c in inspector.get_check_constraints(table)
            if c["name"] == f"{table}_{column}_check"
        )
        # PostgreSQL réécrit « IN (...) » en « = ANY (ARRAY[...]) », ou en « = '...'::text »
        # quand il n'y a qu'une valeur : on extrait les littéraux dans les deux cas.
        allowed = set(re.findall(r"'([^']+)'::(?:character varying|text)", constraint["sqltext"]))
        assert allowed == {member.value for member in enum}, f"{table}.{column}"


def test_orm_round_trip_and_append_only_guard(engine) -> None:
    """Insère une preuve complète par l'ORM, puis vérifie qu'un événement de
    possession ne peut être ni modifié ni supprimé, même par l'ORM."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            user = models.User(email=f"{uuid.uuid4()}@test.local", password_hash="x")  # noqa: S106
            organization = models.Organization(name="Test", is_personal=True)
            session.add_all([user, organization])
            session.flush()
            evidence = models.Evidence(
                organization_id=organization.id, owner_id=user.id, title="Dossier test"
            )
            session.add(evidence)
            session.flush()
            custody_event = models.CustodyEvent(
                evidence_id=evidence.id,
                actor_id=user.id,
                event_type="FILE_UPLOADED",
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                event_hash="a" * 64,
            )
            session.add(custody_event)
            session.flush()
            session.refresh(evidence)
            session.refresh(custody_event)

            # Valeurs par défaut fournies par la base.
            assert evidence.status == EvidenceStatus.RECEIVED
            assert custody_event.event_data == {}
            assert custody_event.canonicalization == "JCS-RFC8785"

            # Chaque tentative a lieu dans un point de sauvegarde, annulé ensuite.
            savepoint = session.begin_nested()
            custody_event.event_type = "FALSIFIED"
            with pytest.raises(AppendOnlyViolation):
                session.flush()
            savepoint.rollback()

            savepoint = session.begin_nested()
            session.delete(custody_event)
            with pytest.raises(AppendOnlyViolation):
                session.flush()
            savepoint.rollback()
        finally:
            session.close()
            transaction.rollback()


def test_registry_declares_every_migrated_table(engine) -> None:
    in_database = set(inspect(engine).get_table_names()) - IGNORED_TABLES
    assert set(Base.metadata.tables) == in_database
