"""Classe de base des modèles SQLAlchemy.

Les modèles ORM seront écrits en phase 2, module par module (app/<module>/models.py),
et devront correspondre exactement au schéma créé par les migrations Alembic.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
