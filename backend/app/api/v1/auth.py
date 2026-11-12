"""Routes /api/v1/auth. Aucune logique ici : tout est dans app.auth.service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.cookies import clear_auth_cookies, set_auth_cookies
from app.auth.dependencies import Client, CurrentSession
from app.auth.schemas import LoginRequest, MeResponse, OrganizationOut, RegisterRequest, UserOut
from app.auth.security import csrf_token_for
from app.auth.service import AuthenticatedSession, OpenedSession
from app.database.session import get_db
from app.organizations.service import get_personal_membership

router = APIRouter(prefix="/auth", tags=["auth"])

Db = Annotated[Session, Depends(get_db)]

INVALID_CREDENTIALS = "Courriel ou mot de passe incorrect."


def _me(db: Session, current: OpenedSession | AuthenticatedSession) -> MeResponse:
    membership = get_personal_membership(db, current.user.id)
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Aucune organisation.")
    return MeResponse(
        user=UserOut(
            id=current.user.id, email=current.user.email, created_at=current.user.created_at
        ),
        organization=OrganizationOut(
            id=membership.organization.id,
            name=membership.organization.name,
            is_personal=membership.organization.is_personal,
            role=membership.role,
        ),
        csrf_token=csrf_token_for(current.token),
        session_expires_at=current.session.expires_at,
    )


def _start_session(response: Response, db: Session, opened: OpenedSession) -> MeResponse:
    me = _me(db, opened)
    set_auth_cookies(response, opened.token, me.csrf_token)
    return me


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=MeResponse)
def register(body: RegisterRequest, response: Response, db: Db, client: Client) -> MeResponse:
    """Crée un compte et son organisation personnelle, puis connecte l'utilisateur."""
    try:
        opened = service.register_user(db, body.email, body.password, client)
    except service.EmailAlreadyRegisteredError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Un compte existe déjà pour ce courriel."
        ) from None
    return _start_session(response, db, opened)


@router.post("/login", response_model=MeResponse)
def login(body: LoginRequest, response: Response, db: Db, client: Client) -> MeResponse:
    try:
        opened = service.authenticate(db, body.email, body.password, client)
    except service.InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS) from None
    return _start_session(response, db, opened)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current: CurrentSession, db: Db, client: Client) -> Response:
    service.revoke_session(db, current.session, client)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=MeResponse)
def me(current: CurrentSession, db: Db) -> MeResponse:
    return _me(db, current)
