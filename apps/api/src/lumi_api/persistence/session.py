from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from lumi_api.config import Settings, get_settings


def require_database_url(settings: Settings | None = None) -> str:
    resolved = settings or get_settings()
    if not resolved.database_url:
        raise RuntimeError("DATABASE_URL is required for persistence")
    if not resolved.database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError("DATABASE_URL must use postgresql+asyncpg://")
    return resolved.database_url


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    return create_async_engine(
        require_database_url(settings),
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        async with session.begin():
            yield session
