"""Tests unitaires des primitives de sécurité (sans base de données)."""

import hashlib

from fastapi import Response

from app.auth import security
from app.auth.cookies import set_auth_cookies
from app.core.config import Settings


def test_password_hash_is_argon2id_and_salted() -> None:
    first = security.hash_password("une phrase de passe solide")
    second = security.hash_password("une phrase de passe solide")
    assert first.startswith("$argon2id$")
    assert first != second  # sel aléatoire : deux empreintes différentes
    assert "une phrase de passe solide" not in first


def test_verify_password() -> None:
    stored = security.hash_password("une phrase de passe solide")
    assert security.verify_password(stored, "une phrase de passe solide")
    assert not security.verify_password(stored, "une phrase de passe solidE")
    assert not security.verify_password("pas une empreinte", "x")


def test_session_token_is_random_and_only_its_sha256_is_stored() -> None:
    tokens = {security.new_session_token() for _ in range(100)}
    assert len(tokens) == 100
    token = tokens.pop()
    assert len(token) >= 43  # 32 octets en base64url
    assert security.hash_session_token(token) == hashlib.sha256(token.encode()).hexdigest()


def test_csrf_token_is_bound_to_the_session() -> None:
    token, other = security.new_session_token(), security.new_session_token()
    csrf = security.csrf_token_for(token)
    assert security.csrf_token_is_valid(token, csrf)
    assert not security.csrf_token_is_valid(other, csrf)
    tampered = csrf[:-1] + ("1" if csrf[-1] == "0" else "0")  # toujours différent
    assert not security.csrf_token_is_valid(token, tampered)
    assert token not in csrf


def _set_cookie_headers(settings: Settings) -> dict[str, str]:
    response = Response()
    set_auth_cookies(response, "session-token", "csrf-token", settings)
    headers = response.headers.getlist("set-cookie")
    return {header.split("=", 1)[0]: header for header in headers}


def test_cookies_in_production_are_secure_host_prefixed_httponly() -> None:
    cookies = _set_cookie_headers(Settings(app_env="production", session_lifetime_hours=8))
    session = cookies["__Host-veritas_session"]
    csrf = cookies["__Host-veritas_csrf"]
    for header in (session, csrf):
        assert "Secure" in header
        assert "Path=/" in header
        assert "SameSite=lax" in header
        assert "Max-Age=28800" in header
        assert "Domain" not in header
    assert "HttpOnly" in session
    assert "HttpOnly" not in csrf  # le frontend doit pouvoir le lire


def test_cookies_in_development_are_not_secure() -> None:
    cookies = _set_cookie_headers(Settings(app_env="development"))
    assert set(cookies) == {"veritas_session", "veritas_csrf"}
    assert all("Secure" not in header for header in cookies.values())


def test_client_ip_is_recorded_only_when_it_is_an_ip() -> None:
    from app.auth.dependencies import _valid_ip

    assert _valid_ip("203.0.113.7") == "203.0.113.7"
    assert _valid_ip("2001:db8::1") == "2001:db8::1"
    assert _valid_ip("testclient") is None
    assert _valid_ip(None) is None
