from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def app_engine() -> Iterator[Engine]:
    """Connexion avec le compte de l'API (DATABASE_URL), comme en production."""
    engine = create_engine(get_settings().database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def owner_engine() -> Iterator[Engine]:
    """Connexion avec le compte propriétaire (MIGRATION_DATABASE_URL)."""
    engine = create_engine(get_settings().migration_database_url)
    yield engine
    engine.dispose()


def _database_available() -> bool:
    try:
        engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 2})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False
    return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Ignore les tests d'intégration si PostgreSQL n'est pas accessible."""
    if _database_available():
        return
    skip = pytest.mark.skip(reason="PostgreSQL inaccessible (DATABASE_URL)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
