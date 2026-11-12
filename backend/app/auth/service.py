"""Cas d'usage de l'authentification : inscription, connexion, session, déconnexion.

Chaque fonction publique correspond à une opération complète et valide sa propre
transaction : soit tout est enregistré (compte, organisation, session, journal),
soit rien.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.models import AccessOutcome
from app.audit.service import AuditAction, ClientInfo, record_access
from app.auth.models import User, UserSession
from app.auth.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    password_needs_rehash,
    spend_password_verification_time,
    verify_password,
)
from app.core.config import get_settings
from app.organizations.service import create_personal_organization


class EmailAlreadyRegisteredError(Exception):
    """Un compte existe déjà pour ce courriel (sans distinction de casse)."""


class InvalidCredentialsError(Exception):
    """Courriel inconnu, mot de passe faux ou compte désactivé : volontairement indistincts."""


@dataclass(frozen=True)
class OpenedSession:
    """Session créée. `token` n'existe qu'ici, en mémoire, le temps de poser le cookie."""

    user: User
    session: UserSession
    token: str


@dataclass(frozen=True)
class AuthenticatedSession:
    """Session valide retrouvée à partir du cookie d'une requête."""

    user: User
    session: UserSession
    token: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _find_user_by_email(db: Session, email: str) -> User | None:
    # Même expression que l'index unique uq_users_email_lower : LOWER(email).
    return db.scalars(select(User).where(func.lower(User.email) == normalize_email(email))).first()


def _open_session(db: Session, user: User, client: ClientInfo) -> tuple[UserSession, str]:
    token = new_session_token()
    lifetime = timedelta(hours=get_settings().session_lifetime_hours)
    user_session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=datetime.now(UTC) + lifetime,
        ip_address=client.ip_address,
        user_agent=client.user_agent[:512] if client.user_agent else None,
    )
    db.add(user_session)
    db.flush()
    return user_session, token


def register_user(db: Session, email: str, password: str, client: ClientInfo) -> OpenedSession:
    """Crée le compte, son organisation personnelle (OWNER) et une première session."""
    if _find_user_by_email(db, email) is not None:
        raise EmailAlreadyRegisteredError
    try:
        user = User(email=normalize_email(email), password_hash=hash_password(password))
        db.add(user)
        db.flush()
        organization = create_personal_organization(db, user.id)
        user_session, token = _open_session(db, user, client)
        record_access(
            db,
            action=AuditAction.REGISTER,
            outcome=AccessOutcome.SUCCESS,
            client=client,
            user_id=user.id,
            organization_id=organization.id,
            resource_type="session",
            resource_id=user_session.id,
        )
        db.commit()
    except IntegrityError as error:
        # Deux inscriptions simultanées avec le même courriel : l'index unique tranche.
        db.rollback()
        raise EmailAlreadyRegisteredError from error
    return OpenedSession(user=user, session=user_session, token=token)


def authenticate(db: Session, email: str, password: str, client: ClientInfo) -> OpenedSession:
    """Vérifie les identifiants et ouvre une session.

    Les trois échecs possibles (courriel inconnu, mauvais mot de passe, compte
    désactivé) lèvent la même erreur, après le même calcul Argon2.
    """
    user = _find_user_by_email(db, email)
    if user is None:
        spend_password_verification_time(password)
        valid = False
    else:
        valid = verify_password(user.password_hash, password) and user.is_active

    if not valid:
        record_access(
            db,
            action=AuditAction.LOGIN,
            outcome=AccessOutcome.DENIED,
            client=client,
            user_id=user.id if user else None,
        )
        db.commit()
        raise InvalidCredentialsError

    if password_needs_rehash(user.password_hash):
        # Les paramètres Argon2 ont été renforcés depuis la création de l'empreinte :
        # c'est le seul moment où l'on connaît le mot de passe pour la recalculer.
        user.password_hash = hash_password(password)
        user.updated_at = func.now()

    user_session, token = _open_session(db, user, client)
    record_access(
        db,
        action=AuditAction.LOGIN,
        outcome=AccessOutcome.SUCCESS,
        client=client,
        user_id=user.id,
        resource_type="session",
        resource_id=user_session.id,
    )
    db.commit()
    return OpenedSession(user=user, session=user_session, token=token)


def resolve_session(db: Session, token: str) -> AuthenticatedSession | None:
    """Retrouve la session d'un jeton, si elle est valide : ni révoquée, ni expirée,
    et son utilisateur toujours actif. Comparaison faite par la base, sur l'empreinte."""
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > func.now(),
            User.is_active.is_(True),
        )
    ).first()
    if row is None:
        return None
    user_session, user = row
    return AuthenticatedSession(user=user, session=user_session, token=token)


def revoke_session(db: Session, user_session: UserSession, client: ClientInfo) -> None:
    """Déconnexion : la session est marquée révoquée (la ligne est conservée)."""
    user_session.revoked_at = datetime.now(UTC)
    record_access(
        db,
        action=AuditAction.LOGOUT,
        outcome=AccessOutcome.SUCCESS,
        client=client,
        user_id=user_session.user_id,
        resource_type="session",
        resource_id=user_session.id,
    )
    db.commit()
