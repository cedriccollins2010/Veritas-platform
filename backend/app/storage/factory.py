"""Choix de l'implémentation de stockage selon la configuration (STORAGE_BACKEND)."""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.storage.base import Storage
from app.storage.local import LocalStorage


def create_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        # Import tardif : boto3 n'est chargé que si le stockage S3 est utilisé.
        import boto3
        from botocore.config import Config

        from app.storage.s3 import S3Storage

        if not settings.s3_bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 exige S3_BUCKET.")
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            # Adressage « chemin » (http://hote/bucket/cle) : accepté par AWS et par
            # les services compatibles S3 auto-hébergés, qui gèrent mal l'autre forme.
            config=Config(s3={"addressing_style": "path"}, retries={"mode": "standard"}),
        )
        return S3Storage(client, settings.s3_bucket)
    return LocalStorage(settings.local_storage_path)


@lru_cache
def get_storage() -> Storage:
    """Stockage de l'application (créé une fois). Dépendance FastAPI pour les routes."""
    return create_storage(get_settings())
