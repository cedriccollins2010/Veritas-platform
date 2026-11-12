"""Moteur SQLAlchemy et dépendance FastAPI fournissant une session par requête."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Crée le moteur au premier appel seulement.

    Le moteur n'est pas créé à l'import du module : l'application peut ainsi
    démarrer (et répondre à /health) même si la base est momentanément absente.
    """
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : ouvre une session, la ferme à la fin de la requête."""
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


def database_is_reachable(session: Session) -> bool:
    """Vérifie que PostgreSQL répond à une requête triviale."""
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
