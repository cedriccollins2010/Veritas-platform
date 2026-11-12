"""Dépendances FastAPI de l'authentification, à réutiliser dans toutes les routes.

    @router.get("/evidence")
    def list_evidence(user: CurrentUser, org: CurrentOrganization): ...

Une route qui déclare CurrentUser ou CurrentOrganization répond 401 sans session valide.
"""

import ipaddress
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit.service import ClientInfo
from app.auth.cookies import session_cookie_name
from app.auth.models import User
from app.auth.service import AuthenticatedSession, resolve_session
from app.database.session import get_db
from app.organizations.service import Membership, get_personal_membership

NOT_AUTHENTICATED = "Authentification requise."


def get_client_info(request: Request) -> ClientInfo:
    """Adresse IP et navigateur de la requête, pour le journal des accès.

    Derrière un proxy (phase 5), l'adresse viendra de l'en-tête X-Forwarded-For posé
    par ce proxy de confiance, configuré dans uvicorn (--forwarded-allow-ips).
    """
    return ClientInfo(
        ip_address=_valid_ip(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )


def _valid_ip(host: str | None) -> str | None:
    """L'adresse seulement si c'est une IP (la colonne est de type INET). Un hôte d'un
    autre genre (socket Unix, client de test) est enregistré comme inconnu plutôt que
    de faire échouer la connexion."""
    if host is None:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def get_current_session(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> AuthenticatedSession:
    token = request.cookies.get(session_cookie_name())
    authenticated = resolve_session(db, token) if token else None
    if authenticated is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_AUTHENTICATED)
    return authenticated


def get_current_user(
    current: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> User:
    return current.user


def get_current_organization(
    current: Annotated[AuthenticatedSession, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> Membership:
    """Organisation au nom de laquelle agit l'utilisateur.

    MVP : son organisation personnelle. Quand un utilisateur pourra appartenir à
    plusieurs organisations (après le MVP), l'organisation choisie sera lue dans la
    requête, et son appartenance vérifiée ici.
    """
    membership = get_personal_membership(db, current.user.id)
    if membership is None:
        # Ne devrait pas arriver : l'organisation est créée avec le compte.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Aucune organisation.")
    return membership


CurrentSession = Annotated[AuthenticatedSession, Depends(get_current_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrganization = Annotated[Membership, Depends(get_current_organization)]
Client = Annotated[ClientInfo, Depends(get_client_info)]
