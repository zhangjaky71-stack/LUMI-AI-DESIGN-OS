from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from lumi_api.config import get_settings
from lumi_api.persistence import models as _models  # noqa: F401
from lumi_api.persistence.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
MIGRATION_ADVISORY_LOCK_ID = 7_204_726_001


def migration_url() -> str:
    settings = get_settings()
    value = settings.migration_database_url
    if not value:
        raise RuntimeError("MIGRATION_DATABASE_URL is required for Alembic")
    if not value.startswith("postgresql+asyncpg://"):
        raise RuntimeError("MIGRATION_DATABASE_URL must use postgresql+asyncpg://")
    return value


def run_migrations_offline() -> None:
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    acquired = connection.exec_driver_sql(
        "SELECT pg_try_advisory_lock(%s)",
        (MIGRATION_ADVISORY_LOCK_ID,),
    ).scalar_one()
    if acquired is not True:
        raise RuntimeError("another LUMI database migration is already running")

    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=False,
        )
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.exec_driver_sql(
            "SELECT pg_advisory_unlock(%s)",
            (MIGRATION_ADVISORY_LOCK_ID,),
        )


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
