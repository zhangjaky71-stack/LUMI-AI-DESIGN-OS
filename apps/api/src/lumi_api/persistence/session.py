# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    app_url: str
    migration_url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_recycle_seconds: int = 1800

    @classmethod
    def from_env(cls) -> DatabaseSettings:
        app_url = os.environ["LUMI_DATABASE_URL"]
        return cls(
            app_url=app_url,
            migration_url=os.environ.get("LUMI_DATABASE_MIGRATION_URL", app_url),
            pool_size=int(os.environ.get("LUMI_DATABASE_POOL_SIZE", "10")),
            max_overflow=int(os.environ.get("LUMI_DATABASE_MAX_OVERFLOW", "20")),
            pool_recycle_seconds=int(
                os.environ.get("LUMI_DATABASE_POOL_RECYCLE_SECONDS", "1800")
            ),
        )


def create_app_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        settings.app_url,
        pool_pre_ping=True,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_recycle=settings.pool_recycle_seconds,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def tenant_session(
    session_factory: async_sessionmaker[AsyncSession], organization_id: UUID
) -> AsyncIterator[AsyncSession]:
    """Set tenant context after application-layer membership authorization."""

    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_id)},
        )
        yield session
