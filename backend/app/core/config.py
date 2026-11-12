"""Configuration de l'application, lue depuis les variables d'environnement.

Aucun secret ne doit être écrit dans ce fichier : les valeurs par défaut ne servent
qu'au développement local. En staging et en production, chaque valeur vient de
l'environnement (fichier .env non versionné ou gestionnaire de secrets).
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"

    # Base de données. En Docker Compose, l'hôte est « db » ; en local, « localhost ».
    # Compte de l'API : membre de veritas_app, privilèges minimaux (migration 0002).
    database_url: str = "postgresql+psycopg://veritas_app_user:change_me_app@localhost:5432/veritas"
    # Compte propriétaire des tables, utilisé uniquement par Alembic. Jamais transmis à
    # l'API en fonctionnement : il peut désactiver le déclencheur append-only.
    migration_database_url: str = (
        "postgresql+psycopg://veritas_user:change_me@localhost:5432/veritas"
    )

    # Origines autorisées à appeler l'API depuis un navigateur (frontend Next.js).
    # Format dans .env : CORS_ORIGINS=http://localhost:3000,https://app.exemple.ca
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Taille maximale d'un fichier téléversé, en mégaoctets (document de référence : 500 Mo).
    max_upload_size_mb: int = 500

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Retourne la configuration (lue une seule fois, puis mise en cache)."""
    return Settings()
