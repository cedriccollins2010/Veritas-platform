"""Tests d'intégration de /api/v1/auth (issue #3).

Chaque test s'exécute dans une transaction annulée à la fin : la base reste propre.
L'API utilise le compte applicatif (DATABASE_URL), comme en production.
"""

import hashlib
import logging
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import security
from app.auth.cookies import CSRF_HEADER, csrf_cookie_name, session_cookie_name
from app.auth.csrf import CSRF_EXEMPT_PATHS
from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"
WRONG_PASSWORD = "mauvais mot de passe"
LOGIN = "/api/v1/auth/login"


def _email() -> str:
    return f"analyste-{uuid.uuid4().hex[:8]}@exemple.test"


def _register(api: TestClient, email: str | None = None, password: str = PASSWORD):
    body = {"email": email or _email(), "password": password}
    return api.post("/api/v1/auth/register", json=body)


def _csrf(api: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: api.cookies.get(csrf_cookie_name())}


# --- Inscription -------------------------------------------------------------------


def test_register_creates_user_personal_organization_and_session(api, db_session) -> None:
    email = _email()
    response = _register(api, email.upper())

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == email  # normalisé en minuscules
    assert body["organization"]["is_personal"] is True
    assert body["organization"]["role"] == "OWNER"
    assert body["csrf_token"] == api.cookies.get(csrf_cookie_name())

    stored = db_session.execute(
        text(
            "SELECT u.password_hash, m.role, o.is_personal FROM users u "
            "JOIN organization_members m ON m.user_id = u.id "
            "JOIN organizations o ON o.id = m.organization_id WHERE u.email = :e"
        ),
        {"e": email},
    ).one()
    assert stored.password_hash.startswith("$argon2id$")
    assert PASSWORD not in stored.password_hash
    assert (stored.role, stored.is_personal) == ("OWNER", True)


def test_register_rejects_duplicate_email_case_insensitively(api) -> None:
    email = _email()
    assert _register(api, email).status_code == 201
    response = _register(api, email.upper())
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "pas-une-adresse", "password": PASSWORD},
        {"email": "a@b", "password": PASSWORD},
        {"email": "analyste@exemple.test", "password": "trop court"},
        {"email": "analyste@exemple.test", "password": "x" * 129},
        {"email": "analyste@exemple.test", "password": PASSWORD, "role": "ADMIN"},
    ],
)
def test_register_validates_input(api, payload) -> None:
    assert api.post("/api/v1/auth/register", json=payload).status_code == 422


def test_cookies_flags(api) -> None:
    response = _register(api)
    set_cookies = {h.split("=", 1)[0]: h for h in response.headers.get_list("set-cookie")}
    session_cookie = set_cookies[session_cookie_name()]
    csrf_cookie = set_cookies[csrf_cookie_name()]
    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    for header in (session_cookie, csrf_cookie):
        assert "SameSite=lax" in header
        assert f"Max-Age={get_settings().session_lifetime_hours * 3600}" in header
        assert ("Secure" in header) == get_settings().secure_cookies


# --- Connexion ---------------------------------------------------------------------


def test_login_and_me(api) -> None:
    email = _email()
    _register(api, email)
    api.cookies.clear()

    assert api.get("/api/v1/auth/me").status_code == 401
    response = api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200

    me = api.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email
    assert me.json()["csrf_token"] == api.cookies.get(csrf_cookie_name())


def test_wrong_password_and_unknown_email_get_the_same_answer(api) -> None:
    email = _email()
    _register(api, email)
    api.cookies.clear()

    wrong = api.post(LOGIN, json={"email": email, "password": WRONG_PASSWORD})
    unknown = api.post("/api/v1/auth/login", json={"email": _email(), "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert session_cookie_name() not in api.cookies


def test_unknown_email_costs_one_argon2_verification(api, monkeypatch) -> None:
    """Même travail cryptographique dans les deux cas : le temps ne trahit pas le compte."""
    email = _email()
    _register(api, email)
    calls: list[str] = []
    real_hasher = security._password_hasher

    class CountingHasher:
        def verify(self, stored, password):
            calls.append("verify")
            return real_hasher.verify(stored, password)

        def __getattr__(self, name):
            return getattr(real_hasher, name)

    monkeypatch.setattr(security, "_password_hasher", CountingHasher())

    durations = {}
    for label, login_email in (("wrong", email), ("unknown", _email())):
        calls.clear()
        start = time.perf_counter()
        api.post(LOGIN, json={"email": login_email, "password": WRONG_PASSWORD})
        durations[label] = time.perf_counter() - start
        assert calls == ["verify"], label

    # Argon2 domine : les deux durées restent du même ordre (marge large contre les aléas).
    assert 1 / 3 < durations["wrong"] / durations["unknown"] < 3


def test_inactive_user_cannot_log_in(api, db_session) -> None:
    email = _email()
    _register(api, email)
    api.cookies.clear()
    db_session.execute(text("UPDATE users SET is_active = FALSE WHERE email = :e"), {"e": email})
    response = api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 401


def test_login_attempts_are_logged_without_secrets(api, db_session) -> None:
    email = _email()
    user_id = _register(api, email).json()["user"]["id"]
    api.cookies.clear()
    api.post("/api/v1/auth/login", json={"email": email, "password": "mauvais mot de passe"})
    api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

    rows = db_session.execute(
        text("SELECT action, outcome FROM access_logs WHERE user_id = :u"),
        {"u": user_id},
    ).all()
    # created_at est identique dans une même transaction de test : on compare des ensembles.
    assert sorted(rows) == sorted(
        [("auth.register", "SUCCESS"), ("auth.login", "DENIED"), ("auth.login", "SUCCESS")]
    )
    logged = db_session.execute(text("SELECT string_agg(a::text, ' ') FROM access_logs a")).scalar()
    assert "mauvais mot de passe" not in logged
    assert PASSWORD not in logged


# --- Jeton de session ---------------------------------------------------------------


def test_session_token_never_stored_or_logged(api, db_session, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    _register(api)
    token = api.cookies.get(session_cookie_name())
    digest = hashlib.sha256(token.encode()).hexdigest()

    sessions = db_session.execute(text("SELECT string_agg(s::text, ' ') FROM sessions s")).scalar()
    logs = db_session.execute(text("SELECT string_agg(a::text, ' ') FROM access_logs a")).scalar()
    assert token not in sessions
    assert digest in sessions
    assert token not in logs
    assert token not in caplog.text


def test_revoked_session_is_refused(api) -> None:
    _register(api)
    token = api.cookies.get(session_cookie_name())
    assert api.post("/api/v1/auth/logout", headers=_csrf(api)).status_code == 204
    assert session_cookie_name() not in api.cookies

    # Rejouer l'ancien cookie (volé, par exemple) ne sert plus à rien.
    api.cookies.set(session_cookie_name(), token)
    assert api.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_refused(api, db_session) -> None:
    _register(api)
    token = api.cookies.get(session_cookie_name())
    db_session.execute(
        text(
            "UPDATE sessions SET created_at = NOW() - INTERVAL '2 hours', "
            "expires_at = NOW() - INTERVAL '1 second' WHERE token_hash = :h"
        ),
        {"h": security.hash_session_token(token)},
    )
    assert api.get("/api/v1/auth/me").status_code == 401


def test_forged_session_cookie_is_refused(api) -> None:
    api.cookies.set(session_cookie_name(), security.new_session_token())
    assert api.get("/api/v1/auth/me").status_code == 401


# --- CSRF -----------------------------------------------------------------------------


def test_logout_requires_valid_csrf_token(api) -> None:
    _register(api)
    assert api.post("/api/v1/auth/logout").status_code == 403
    assert api.post("/api/v1/auth/logout", headers={CSRF_HEADER: "0" * 64}).status_code == 403
    # Le jeton CSRF d'une autre session ne vaut rien ici.
    other = security.csrf_token_for(security.new_session_token())
    assert api.post("/api/v1/auth/logout", headers={CSRF_HEADER: other}).status_code == 403
    # La session n'a pas été révoquée par ces tentatives.
    assert api.get("/api/v1/auth/me").status_code == 200
    assert api.post("/api/v1/auth/logout", headers=_csrf(api)).status_code == 204


def test_every_write_route_requires_csrf_except_documented_exemptions(api) -> None:
    """Garde-fou pour les routes futures : toute route d'écriture non exemptée doit
    répondre 403 sans jeton, même avec une session valide."""
    _register(api)
    write_routes = [
        (path, method.upper())
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() not in {"GET", "HEAD", "OPTIONS"} and path not in CSRF_EXEMPT_PATHS
    ]
    assert write_routes, "au moins /auth/logout"
    for path, method in write_routes:
        url = path.replace("{", "").replace("}", "")  # paramètres de chemin quelconques
        response = api.request(method, url, json={})
        assert response.status_code == 403, f"{method} {path}"


def test_login_requires_json_body(api) -> None:
    """Un formulaire HTML d'un autre site ne peut pas envoyer de JSON."""
    response = api.post(
        "/api/v1/auth/login",
        content=f'{{"email": "{_email()}", "password": "{PASSWORD}"}}',
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 415


def test_login_from_foreign_origin_is_refused(api) -> None:
    email = _email()
    _register(api, email)
    api.cookies.clear()
    response = api.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"Origin": "https://site-malveillant.exemple"},
    )
    assert response.status_code == 403
    allowed = get_settings().cors_origins[0]
    response = api.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"Origin": allowed},
    )
    assert response.status_code == 200
