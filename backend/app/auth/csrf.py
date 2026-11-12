"""Protection CSRF, appliquée à toutes les routes de /api/v1.

L'attaque visée : un site malveillant fait envoyer par le navigateur de la victime une
requête vers VERITAS (un formulaire caché, par exemple). Le navigateur y joint les
cookies de VERITAS, donc la requête semble venir de la victime connectée.

Règle : toute requête qui modifie des données (méthode autre que GET, HEAD, OPTIONS)
doit porter dans l'en-tête X-CSRF-Token le jeton dérivé de sa session. Un site tiers
ne peut ni lire ce jeton, ni le calculer. La règle est posée une seule fois, sur le
routeur /api/v1 : une nouvelle route en bénéficie sans rien déclarer.

Exceptions : l'inscription et la connexion, faites avant qu'une session existe. Elles
exigent un corps JSON (un formulaire HTML ne peut pas en envoyer) et, si le navigateur
indique une origine, que ce soit une origine autorisée (CORS_ORIGINS).
"""

from fastapi import HTTPException, Request, status

from app.auth.cookies import CSRF_HEADER, session_cookie_name
from app.auth.security import csrf_token_is_valid
from app.core.config import get_settings

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Chemins complets des routes qui modifient des données sans session préalable.
# tests/test_auth.py vérifie que toute autre route d'écriture exige le jeton.
CSRF_EXEMPT_PATHS = frozenset({"/api/v1/auth/register", "/api/v1/auth/login"})

CSRF_FAILED = "Jeton CSRF absent ou invalide."


def _require_json_from_allowed_origin(request: Request) -> None:
    content_type = request.headers.get("content-type", "")
    if content_type.split(";")[0].strip().lower() != "application/json":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Corps JSON attendu.")
    origin = request.headers.get("origin")
    if origin is not None and origin not in get_settings().cors_origins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Origine non autorisée.")


def csrf_protect(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    if request.url.path in CSRF_EXEMPT_PATHS:
        _require_json_from_allowed_origin(request)
        return
    session_token = request.cookies.get(session_cookie_name())
    candidate = request.headers.get(CSRF_HEADER)
    if not session_token or not candidate or not csrf_token_is_valid(session_token, candidate):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=CSRF_FAILED)
