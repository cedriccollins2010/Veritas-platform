"""Corps des requêtes et réponses de /api/v1/auth."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.organizations.models import MemberRole

# Longueur minimale : 12 caractères (OWASP ASVS 5.0, V6.2.1). Maximale : 128, pour
# laisser les phrases de passe tout en bornant le coût d'Argon2 sur une entrée géante.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
EMAIL_MAX_LENGTH = 255


def _check_email(value: str) -> str:
    """Contrôle volontairement simple : la vraie preuve d'une adresse sera le courriel
    de vérification (phase 5). On refuse seulement ce qui ne peut pas être une adresse."""
    candidate = value.strip()
    local, _, domain = candidate.rpartition("@")
    if not local or "." not in domain or any(c.isspace() for c in candidate):
        raise ValueError("Adresse courriel invalide.")
    return candidate


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=EMAIL_MAX_LENGTH)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    _validate_email = field_validator("email")(_check_email)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Pas de règle de format à la connexion : un identifiant mal formé est simplement
    # un identifiant inconnu, et reçoit la même réponse qu'un mauvais mot de passe.
    email: str = Field(min_length=1, max_length=EMAIL_MAX_LENGTH)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    is_personal: bool
    role: MemberRole


class MeResponse(BaseModel):
    user: UserOut
    organization: OrganizationOut
    # Copie du cookie CSRF, pour un client qui ne lit pas les cookies.
    csrf_token: str
    session_expires_at: datetime
