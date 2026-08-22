from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from lumi_api.config import get_settings
from lumi_api.persistence import models as _models  # noqa: F401
from lumi_api.persistence.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
MIGRATION_ADVISORY_LOCK_ID = 7_204_726_001
ALEMBIC_VERSION_COLUMN_LENGTH = 255
MIGRATION_OWNED_TABLES = frozenset(
    {
        "agent_graph_definitions",
        "agent_run_control",
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "store_migrations",
        "store",
    }
)


def migration_url() -> str:
    settings = get_settings()
    value = settings.migration_database_url
    if not value:
        raise RuntimeError("MIGRATION_DATABASE_URL is required for Alembic")
    if not value.startswith("postgresql+asyncpg://"):
        raise RuntimeError("MIGRATION_DATABASE_URL must use postgresql+asyncpg://")
    return value


def _include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object,
) -> bool:
    if not reflected:
        return True
    if type_ == "table" and name in MIGRATION_OWNED_TABLES:
        return False
    table_name = getattr(getattr(object_, "table", None), "name", None)
    return table_name not in MIGRATION_OWNED_TABLES


def run_migrations_offline() -> None:
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=False,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _ensure_alembic_version_capacity(connection: Connection) -> None:
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num varchar({ALEMBIC_VERSION_COLUMN_LENGTH}) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
            """
        )
    )
    connection.execute(
        text(
            "ALTER TABLE alembic_version "
            f"ALTER COLUMN version_num TYPE varchar({ALEMBIC_VERSION_COLUMN_LENGTH})"
        )
    )


def _release_migration_lock(connection: Connection) -> None:
    connection.execute(
        text("SELECT pg_advisory_unlock(:lock_id)"),
        {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
    )
    if connection.in_transaction():
        connection.commit()


def do_run_migrations(connection: Connection) -> None:
    acquired = connection.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
    ).scalar_one()
    if acquired is not True:
        raise RuntimeError("another LUMI database migration is already running")

    try:
        _ensure_alembic_version_capacity(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=False,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    except Exception:
        if connection.in_transaction():
            connection.rollback()
        try:
            _release_migration_lock(connection)
        except Exception:
            if connection.in_transaction():
                connection.rollback()
        raise
    else:
        _release_migration_lock(connection)


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = migration_url()
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
