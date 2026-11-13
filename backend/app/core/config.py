"""Configuration de l'application, lue depuis les variables d'environnement.

Aucun secret ne doit être écrit dans ce fichier : les valeurs par défaut ne servent
qu'au développement local. En staging et en production, chaque valeur vient de
l'environnement (fichier .env non versionné ou gestionnaire de secrets).
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
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

    # Dossier des fichiers temporaires pendant un téléversement (None = dossier système).
    # Doit pouvoir contenir MAX_UPLOAD_SIZE_MB par dépôt simultané.
    upload_temp_dir: Path | None = None

    # Stockage des fichiers originaux : « local » (disque) ou « s3 » (compatible S3).
    storage_backend: Literal["local", "s3"] = "local"
    # Dossier du stockage local. Par défaut hors du dépôt, dans le dossier personnel.
    local_storage_path: Path = Path.home() / ".veritas" / "storage"
    # Stockage S3. Les identifiants viennent de AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.
    s3_endpoint_url: str | None = None  # None = AWS ; sinon l'adresse du service compatible
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"

    # Autorité d'horodatage RFC 3161 : DigiCert (développement, pilote) ou FreeTSA (tests).
    tsa_provider: Literal["digicert", "freetsa"] = "digicert"
    # Délai maximal d'un appel à la TSA, en secondes : au-delà, l'horodatage est reporté.
    tsa_timeout_seconds: float = Field(default=10.0, gt=0, le=120)

    # Durée de vie d'une session de connexion, en heures. Au-delà, il faut se reconnecter.
    session_lifetime_hours: int = Field(default=12, ge=1, le=720)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def secure_cookies(self) -> bool:
        """Cookies « Secure » (envoyés seulement en HTTPS) partout sauf en développement,
        où l'API est servie en HTTP sur la machine locale."""
        return self.app_env != "development"


@lru_cache
def get_settings() -> Settings:
    """Retourne la configuration (lue une seule fois, puis mise en cache)."""
    return Settings()
