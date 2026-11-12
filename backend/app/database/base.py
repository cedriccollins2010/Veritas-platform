"""Classe de base des modèles SQLAlchemy.

Les modèles ORM vivent dans chaque module (app/<module>/models.py) et décrivent
exactement le schéma créé par les migrations Alembic. Le test
tests/test_orm_schema.py vérifie cette correspondance sur une vraie base.
"""

from enum import StrEnum

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Convention de nommage identique aux noms que PostgreSQL choisit lui-même quand la
# migration SQL ne nomme pas une contrainte (ex. « evidence_owner_id_fkey »). Ainsi,
# une future migration générée à partir des modèles désignera les contraintes
# existantes par leur vrai nom. Pour les CHECK, le nom donné dans le modèle est un
# suffixe : CheckConstraint(..., name="status_check") devient « evidence_status_check ».
NAMING_CONVENTION = {
    "pk": "%(table_name)s_pkey",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def sql_in(column: str, values: type[StrEnum]) -> str:
    """Expression SQL « column IN ('A', 'B') » construite à partir d'une énumération.

    L'énumération Python reste ainsi la seule liste de valeurs côté application ;
    un test compare cette liste à la contrainte CHECK réellement présente en base.
    """
    quoted = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({quoted})"
