"""Contrôle de disponibilité : l'API et sa base de données sont-elles prêtes ?"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import __version__
from app.database.session import database_is_reachable, get_db

router = APIRouter(tags=["health"])


class ReadinessResponse(BaseModel):
    status: str
    application: str
    version: str
    database: str


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness(response: Response, db: Annotated[Session, Depends(get_db)]) -> ReadinessResponse:
    """Retourne 200 si PostgreSQL répond, 503 sinon."""
    database_ok = database_is_reachable(db)
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if database_ok else "degraded",
        application="VERITAS",
        version=__version__,
        database="up" if database_ok else "down",
    )
