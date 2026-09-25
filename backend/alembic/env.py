# ruff: noqa: I001
import sys
from logging.config import fileConfig
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.engine import Connection

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.base import Base
from fitminiapp_api.models import *  # noqa: F403

config = context.config
# Alembic stores main options in ConfigParser, where ``%`` starts interpolation.
# Database URLs legitimately contain percent-encoded credentials, so escape the
# character for ConfigParser while preserving the URL returned by Alembic.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
if config.config_file_name is not None:
    # Keep application loggers available to tests and migration diagnostics.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
MIGRATION_ADVISORY_LOCK_ID = 626517843


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    def run(connection: Connection) -> None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=config.attributes.get("version_table_schema"),
        )
        with context.begin_transaction():
            if connection.dialect.name == "postgresql":
                # Serialize automatic and manual migrations during container startup.
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
                )
            context.run_migrations()

    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        run(supplied_connection)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
