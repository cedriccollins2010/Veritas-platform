"""Journal des accès (table access_logs).

Les fonctions ajoutent une ligne à la session SQLAlchemy sans valider la transaction :
l'entrée est enregistrée en même temps que l'opération qu'elle décrit.

Ne jamais y écrire de secret : ni mot de passe, ni jeton, ni courriel saisi lors d'un
échec (il pourrait s'agir d'un mot de passe tapé dans le mauvais champ).
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from app.audit.models import AccessLog, AccessOutcome

USER_AGENT_MAX_LENGTH = 512


class AuditAction(StrEnum):
    REGISTER = "auth.register"
    LOGIN = "auth.login"
    LOGOUT = "auth.logout"
    EVIDENCE_CREATE = "evidence.create"
    EVIDENCE_TIMESTAMP = "evidence.timestamp"
    CHAIN_ANCHOR = "evidence.anchor"


@dataclass(frozen=True)
class ClientInfo:
    """Origine d'une requête, telle que vue par le serveur."""

    ip_address: str | None
    user_agent: str | None


def record_access(
    db: Session,
    *,
    action: AuditAction,
    outcome: AccessOutcome,
    client: ClientInfo,
    user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
) -> None:
    user_agent = client.user_agent[:USER_AGENT_MAX_LENGTH] if client.user_agent else None
    db.add(
        AccessLog(
            action=action.value,
            outcome=outcome.value,
            user_id=user_id,
            organization_id=organization_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=client.ip_address,
            user_agent=user_agent,
        )
    )
