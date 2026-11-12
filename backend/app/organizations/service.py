"""Organisations et appartenance des utilisateurs."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.organizations.models import MemberRole, Organization, OrganizationMember

PERSONAL_ORGANIZATION_NAME = "Espace personnel"


@dataclass(frozen=True)
class Membership:
    organization: Organization
    role: MemberRole


def create_personal_organization(db: Session, user_id: uuid.UUID) -> Organization:
    """Crée l'organisation personnelle d'un nouvel utilisateur, qui en est OWNER.

    Ne valide pas la transaction : elle est créée en même temps que le compte.
    """
    organization = Organization(name=PERSONAL_ORGANIZATION_NAME, is_personal=True)
    db.add(organization)
    db.flush()  # attribue organization.id (gen_random_uuid côté base)
    db.add(
        OrganizationMember(
            organization_id=organization.id, user_id=user_id, role=MemberRole.OWNER.value
        )
    )
    return organization


def get_personal_membership(db: Session, user_id: uuid.UUID) -> Membership | None:
    """Organisation personnelle de l'utilisateur et son rôle, si elle existe."""
    row = db.execute(
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user_id, Organization.is_personal.is_(True))
    ).first()
    if row is None:
        return None
    organization, role = row
    return Membership(organization=organization, role=MemberRole(role))
