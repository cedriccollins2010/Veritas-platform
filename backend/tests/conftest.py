from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
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


@pytest.fixture
def db_session(app_engine) -> Iterator[Session]:
    """Session SQLAlchemy dans une transaction annulée à la fin du test (base propre).
    Les commit() du code testé deviennent des points de sauvegarde."""
    with app_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        )
        yield session
        session.close()
        transaction.rollback()


@pytest.fixture
def api(db_session: Session) -> Iterator[TestClient]:
    """Client HTTP de l'API branché sur db_session."""
    app.dependency_overrides[get_db] = lambda: db_session
    # HTTPS : les cookies Secure (hors développement) ne sont renvoyés qu'en HTTPS.
    with TestClient(app, base_url="https://testserver") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


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


@pytest.fixture(scope="session")
def tsa(tmp_path_factory):
    """Autorité d'horodatage de test (OpenSSL), partagée par les tests de la session."""
    from tests.local_tsa import OPENSSL, create_local_tsa

    if OPENSSL is None:
        pytest.skip("openssl absent")
    return create_local_tsa(tmp_path_factory.mktemp("tsa"))


@pytest.fixture(scope="session")
def rogue_tsa(tmp_path_factory):
    """Seconde autorité, absente des racines de confiance des tests."""
    from tests.local_tsa import OPENSSL, create_local_tsa

    if OPENSSL is None:
        pytest.skip("openssl absent")
    return create_local_tsa(tmp_path_factory.mktemp("rogue"), name="Imposteur")
