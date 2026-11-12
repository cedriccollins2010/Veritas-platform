"""Environnement Alembic : applique les migrations sur la base définie par DATABASE_URL."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.database.models import Base

config = context.config
# Les migrations utilisent le compte propriétaire, pas celui de l'API.
config.set_main_option("sqlalchemy.url", get_settings().migration_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Les modèles ORM (app/<module>/models.py, réunis par app.database.models) décrivent
# tout le schéma ; tests/test_orm_schema.py et « alembic check » le vérifient.
# L'autogénération ne voit ni les déclencheurs, ni les fonctions, ni le contenu des
# CHECK : toute migration générée doit être relue, et complétée à la main si besoin.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
