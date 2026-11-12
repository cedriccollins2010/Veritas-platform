"""Registre de tous les modèles ORM.

Importer ce module garantit que chaque table est déclarée dans Base.metadata
(nécessaire pour résoudre les clés étrangères entre modules, pour Alembic et pour
les tests). Il n'est importé ni par base.py ni par les modules métier, ce qui évite
les imports circulaires.
"""

from app.audit.models import AccessLog
from app.auth.models import User, UserSession
from app.custody.models import CustodyEvent
from app.database.base import Base
from app.evidence.models import Evidence, EvidenceFile, HashRecord
from app.organizations.models import Organization, OrganizationMember
from app.timestamp.models import TimestampRecord
from app.verification.models import VerificationRecord

__all__ = [
    "AccessLog",
    "Base",
    "CustodyEvent",
    "Evidence",
    "EvidenceFile",
    "HashRecord",
    "Organization",
    "OrganizationMember",
    "TimestampRecord",
    "User",
    "UserSession",
    "VerificationRecord",
]
