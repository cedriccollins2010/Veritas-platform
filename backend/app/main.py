"""Point d'entrée de l'API VERITAS.

Démarrage local :  uvicorn app.main:app --reload
Documentation :    http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="VERITAS API",
        description="Constitution et vérification indépendante de dossiers de preuve numérique",
        version=__version__,
        # La documentation interactive n'est pas exposée en production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Le frontend s'authentifiera par cookie de session : allow_credentials est requis,
    # ce qui interdit d'utiliser "*" comme origine.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.get("/health", tags=["health"])
    def liveness() -> dict[str, str]:
        """Le processus répond. Ne vérifie pas la base (voir /api/v1/health/ready)."""
        return {"status": "healthy", "application": "VERITAS", "version": __version__}

    app.include_router(api_router)
    return app


app = create_app()
