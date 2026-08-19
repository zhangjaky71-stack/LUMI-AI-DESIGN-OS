from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from lumi_api.persistence.models import AgentRun, Artifact, Asset, AssetRights, Task
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID
from lumi_api.persistence.session import create_engine
from lumi_api.tool_gateway_staging_fixture import (
    AGENT_RUN_ID,
    ARTIFACT_ID,
    SOURCE_ASSET_ID,
    SOURCE_RIGHTS_ID,
    TASK_ID,
    StagingFixtureError,
    materialize,
)

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip(
        "set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests",
        allow_module_level=True,
    )


async def _count(factory: async_sessionmaker, model: type[object], row_id: object) -> int:
    async with factory() as session:
        table_id = getattr(model, "id")
        return int(
            await session.scalar(select(func.count()).select_from(model).where(table_id == row_id))
            or 0
        )


async def _acceptance() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            factory = async_sessionmaker(bind=connection, expire_on_commit=False)
            try:
                async with factory() as session:
                    first = await materialize(session)
                    await session.flush()
                    second = await materialize(session)
                    await session.flush()

                    assert first == second
                    assert first.synthetic_only is True
                    assert first.organization_id == str(ORG_ID)
                    assert first.project_id == str(PROJECT_A_ID)
                    assert first.agent_run_id == str(AGENT_RUN_ID)
                    assert first.task_id == str(TASK_ID)
                    assert first.source_asset_id == str(SOURCE_ASSET_ID)
                    assert first.artifact_id == str(ARTIFACT_ID)

                    agent_run = await session.get(AgentRun, AGENT_RUN_ID)
                    task = await session.get(Task, TASK_ID)
                    source_asset = await session.get(Asset, SOURCE_ASSET_ID)
                    rights = await session.get(AssetRights, SOURCE_RIGHTS_ID)
                    artifact = await session.get(Artifact, ARTIFACT_ID)
                    assert agent_run is not None
                    assert task is not None
                    assert source_asset is not None
                    assert rights is not None
                    assert artifact is not None
                    assert task.organization_id == ORG_ID
                    assert task.project_id == PROJECT_A_ID
                    assert task.agent_run_id == AGENT_RUN_ID
                    assert source_asset.status == "ready"
                    assert source_asset.deleted_at is None
                    assert source_asset.metadata_json["synthetic_only"] is True
                    assert rights.asset_id == SOURCE_ASSET_ID
                    assert rights.source_type == "GENERATED"
                    assert rights.license_type == "OWNED"
                    assert rights.commercial_use == "ALLOWED"
                    assert rights.redistribution == "ALLOWED"
                    assert rights.review_status == "VERIFIED"
                    assert artifact.organization_id == ORG_ID
                    assert artifact.project_id == PROJECT_A_ID
                    assert artifact.metadata_json["synthetic_only"] is True

                    assert await _count(factory, AgentRun, AGENT_RUN_ID) == 1
                    assert await _count(factory, Task, TASK_ID) == 1
                    assert await _count(factory, Asset, SOURCE_ASSET_ID) == 1
                    assert await _count(factory, AssetRights, SOURCE_RIGHTS_ID) == 1
                    assert await _count(factory, Artifact, ARTIFACT_ID) == 1

                    artifact.title = "tampered fixture"
                    await session.flush()
                    with pytest.raises(StagingFixtureError, match="artifact identity collision"):
                        await materialize(session)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_tool_gateway_staging_fixture_is_idempotent_and_fail_closed() -> None:
    asyncio.run(_acceptance())
