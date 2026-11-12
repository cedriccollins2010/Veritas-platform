"""Regroupe toutes les routes de la version 1. Chaque module y ajoutera son routeur."""

from fastapi import APIRouter, Depends

from app.api.v1 import auth, health
from app.auth.csrf import csrf_protect

# csrf_protect s'applique à toutes les routes ci-dessous (voir app/auth/csrf.py).
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(csrf_protect)])
api_router.include_router(health.router)
api_router.include_router(auth.router)
