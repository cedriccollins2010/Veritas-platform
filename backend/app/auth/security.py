"""Primitives de sécurité de l'authentification.

Tout passe par des bibliothèques éprouvées : argon2-cffi pour les mots de passe,
secrets / hashlib / hmac (bibliothèque standard) pour les jetons. Aucun algorithme
n'est implémenté ici.
"""

import hashlib
import hmac
import secrets
from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id avec les paramètres par défaut d'argon2-cffi : profil recommandé par la
# RFC 9106 (64 Mio de mémoire, 3 passes, 4 fils). Chaque essai coûte de la mémoire
# et du temps, ce qui rend une attaque par dictionnaire sur une base volée très lente.
_password_hasher = PasswordHasher()

# 32 octets aléatoires = 256 bits : impossible à deviner. token_urlsafe les encode
# en 43 caractères utilisables dans un cookie.
SESSION_TOKEN_BYTES = 32

# Séparation de domaine : le jeton CSRF est dérivé du jeton de session pour cet
# usage précis, et ne peut servir à rien d'autre.
_CSRF_CONTEXT = b"veritas-csrf-v1"


def hash_password(password: str) -> str:
    """Empreinte Argon2id du mot de passe, avec son sel et ses paramètres inclus."""
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Vrai si le mot de passe correspond. Ne lève jamais d'exception."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Vrai si l'empreinte a été calculée avec des paramètres plus faibles qu'aujourd'hui."""
    return _password_hasher.check_needs_rehash(password_hash)


@cache
def _dummy_password_hash() -> str:
    return _password_hasher.hash(secrets.token_urlsafe(16))


def spend_password_verification_time(password: str) -> None:
    """Effectue une vérification Argon2 inutile.

    Appelée quand le courriel est inconnu : la réponse prend alors le même temps que
    pour un mauvais mot de passe. Sinon, mesurer le temps de réponse suffirait à
    savoir si un courriel a un compte.
    """
    verify_password(_dummy_password_hash(), password)


def new_session_token() -> str:
    """Jeton de session aléatoire, remis au navigateur et jamais stocké tel quel."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Empreinte SHA-256 du jeton : c'est elle, et elle seule, qui va en base.

    Quelqu'un qui lit la table sessions ne peut pas en déduire les jetons, donc ne
    peut pas se faire passer pour les utilisateurs connectés. Un hachage rapide
    suffit ici (contrairement aux mots de passe) : le jeton est aléatoire sur 256 bits.
    """
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_token_for(session_token: str) -> str:
    """Jeton CSRF lié à la session : HMAC-SHA256(clé = jeton de session, message fixe).

    Seul quelqu'un qui connaît le jeton de session peut le calculer. Un site tiers ne
    le peut pas : le cookie de session est HttpOnly et le navigateur ne lui montre
    jamais les cookies de VERITAS. Le jeton CSRF peut être lu par JavaScript sans
    rien révéler du jeton de session (HMAC n'est pas réversible).
    """
    return hmac.new(session_token.encode("ascii"), _CSRF_CONTEXT, hashlib.sha256).hexdigest()


def csrf_token_is_valid(session_token: str, candidate: str) -> bool:
    """Compare en temps constant le jeton CSRF reçu à celui attendu pour cette session."""
    return hmac.compare_digest(csrf_token_for(session_token), candidate)
