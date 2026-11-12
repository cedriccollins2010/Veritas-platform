"""Cookies de l'authentification.

Deux cookies, posés et effacés ensemble :
- le cookie de session, HttpOnly : JavaScript ne peut pas le lire, donc un script
  injecté (XSS) ne peut pas le voler ;
- le cookie CSRF, lisible par JavaScript : le frontend le recopie dans l'en-tête
  X-CSRF-Token de chaque requête qui modifie des données (« double soumission »).

En HTTPS, les noms portent le préfixe __Host- : le navigateur refuse alors un cookie
de ce nom qui ne serait pas Secure, limité à Path=/ et sans attribut Domain. Un
sous-domaine compromis ne peut donc pas imposer sa propre session.
"""

from fastapi import Response

from app.core.config import Settings, get_settings

CSRF_HEADER = "X-CSRF-Token"


def session_cookie_name(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return "__Host-veritas_session" if settings.secure_cookies else "veritas_session"


def csrf_cookie_name(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return "__Host-veritas_csrf" if settings.secure_cookies else "veritas_csrf"


def set_auth_cookies(
    response: Response, session_token: str, csrf_token: str, settings: Settings | None = None
) -> None:
    settings = settings or get_settings()
    common = {
        "max_age": settings.session_lifetime_hours * 3600,
        "path": "/",
        "secure": settings.secure_cookies,
        # Lax : le cookie n'accompagne pas les requêtes POST lancées depuis un autre
        # site, mais suit un lien ordinaire vers VERITAS. Le jeton CSRF couvre le reste.
        "samesite": "lax",
    }
    response.set_cookie(session_cookie_name(settings), session_token, httponly=True, **common)
    response.set_cookie(csrf_cookie_name(settings), csrf_token, httponly=False, **common)


def clear_auth_cookies(response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    cookies = ((session_cookie_name(settings), True), (csrf_cookie_name(settings), False))
    for name, httponly in cookies:
        response.delete_cookie(
            name, path="/", secure=settings.secure_cookies, httponly=httponly, samesite="lax"
        )
