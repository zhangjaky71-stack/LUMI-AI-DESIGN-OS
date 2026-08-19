from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.persistence.models import AgentRun, Artifact, Asset, Task
from lumi_api.persistence.seed import (
    ARTIFACT_ID,
    ASSET_ID,
    ORG_ID,
    PROJECT_A_ID,
    PROJECT_B_ID,
)
from lumi_api.persistence.session import create_engine
from lumi_api.tool_data_control import ToolDataStore

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip(
        "set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests",
        allow_module_level=True,
    )


async def _acceptance() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            factory = async_sessionmaker(bind=connection, expire_on_commit=False)
            session: AsyncSession = factory()
            try:
                agent_run = AgentRun(
                    organization_id=ORG_ID,
                    project_id=PROJECT_A_ID,
                    thread_id=f"tool-data-{uuid4()}",
                    graph_version="tool-data-test-v1",
                    agent_config_version="tool-data-test-v1",
                    status="running",
                    budget_json={},
                )
                session.add(agent_run)
                await session.flush()

                task = Task(
                    organization_id=ORG_ID,
                    project_id=PROJECT_A_ID,
                    agent_run_id=agent_run.id,
                    type="project.query",
                    status="running",
                    input_json={},
                    output_json={},
                    metadata_json={},
                    priority=100,
                    attempt_count=0,
                    max_attempts=3,
                    budget_reserved=Decimal("0"),
                )
                session.add(task)
                await session.flush()

                foreign_asset = Asset(
                    organization_id=ORG_ID,
                    project_id=PROJECT_B_ID,
                    kind="image",
                    source="tool-data-test",
                    original_name="foreign.png",
                    metadata_json={},
                    status="ready",
                )
                foreign_artifact = Artifact(
                    organization_id=ORG_ID,
                    project_id=PROJECT_B_ID,
                    kind="poster",
                    title="Foreign Artifact",
                    metadata_json={},
                )
                session.add_all([foreign_asset, foreign_artifact])
                await session.flush()

                store = ToolDataStore(factory)
                result = await store.query_project(
                    organization_id=ORG_ID,
                    agent_run_id=agent_run.id,
                    task_id=task.id,
                    query="project.summary",
                )
                assert result["project_id"] == str(PROJECT_A_ID)
                assert isinstance(result["name"], str) and result["name"]
                assert result["status"] in {"draft", "active", "paused", "archived"}
                assert isinstance(result["summary"], dict)

                asset = await store.read_asset(
                    organization_id=ORG_ID,
                    agent_run_id=agent_run.id,
                    task_id=task.id,
                    asset_id=ASSET_ID,
                )
                assert asset["asset_id"] == str(ASSET_ID)
                assert asset["project_id"] == str(PROJECT_A_ID)
                assert asset["kind"] == "image"
                asset_json = json.dumps(asset, sort_keys=True)
                assert '"bucket"' not in asset_json
                assert '"object_key"' not in asset_json

                media = await store.inspect_media(
                    organization_id=ORG_ID,
                    agent_run_id=agent_run.id,
                    task_id=task.id,
                    asset_id=ASSET_ID,
                )
                assert media["asset_id"] == str(ASSET_ID)
                assert media["kind"] == "image"
                assert isinstance(media["files"], list)

                artifact = await store.query_artifact(
                    organization_id=ORG_ID,
                    agent_run_id=agent_run.id,
                    task_id=task.id,
                    artifact_id=ARTIFACT_ID,
                )
                assert artifact["artifact_id"] == str(ARTIFACT_ID)
                assert artifact["project_id"] == str(PROJECT_A_ID)
                assert artifact["latest_version"]["version_number"] == 2
                artifact_json = json.dumps(artifact, sort_keys=True)
                assert '"bucket"' not in artifact_json
                assert '"object_key"' not in artifact_json

                with pytest.raises(
                    KeyError,
                    match="TOOL_DATA_ASSET_NOT_FOUND_OR_FORBIDDEN",
                ):
                    await store.read_asset(
                        organization_id=ORG_ID,
                        agent_run_id=agent_run.id,
                        task_id=task.id,
                        asset_id=foreign_asset.id,
                    )

                with pytest.raises(
                    KeyError,
                    match="TOOL_DATA_ARTIFACT_NOT_FOUND_OR_FORBIDDEN",
                ):
                    await store.query_artifact(
                        organization_id=ORG_ID,
                        agent_run_id=agent_run.id,
                        task_id=task.id,
                        artifact_id=foreign_artifact.id,
                    )

                with pytest.raises(
                    KeyError,
                    match="TOOL_DATA_TASK_NOT_FOUND_OR_FORBIDDEN",
                ):
                    await store.query_project(
                        organization_id=uuid4(),
                        agent_run_id=agent_run.id,
                        task_id=task.id,
                        query="project.summary",
                    )

                with pytest.raises(
                    KeyError,
                    match="TOOL_DATA_TASK_NOT_FOUND_OR_FORBIDDEN",
                ):
                    await store.query_project(
                        organization_id=ORG_ID,
                        agent_run_id=uuid4(),
                        task_id=task.id,
                        query="project.summary",
                    )

                with pytest.raises(
                    ValueError,
                    match="TOOL_DATA_PROJECT_QUERY_UNSUPPORTED",
                ):
                    await store.query_project(
                        organization_id=ORG_ID,
                        agent_run_id=agent_run.id,
                        task_id=task.id,
                        query="project.delete",
                    )
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_tool_data_project_asset_artifact_scope_and_query_allowlist() -> None:
    asyncio.run(_acceptance())
