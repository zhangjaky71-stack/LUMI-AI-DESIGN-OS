from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import AgentRun, Task
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID
from lumi_api.persistence.session import create_engine
from lumi_api.tool_data_control import ToolDataStore

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)


async def _acceptance() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
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

                store = ToolDataStore(lambda: session)  # type: ignore[arg-type]
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

                with pytest.raises(KeyError, match="TOOL_DATA_TASK_NOT_FOUND_OR_FORBIDDEN"):
                    await store.query_project(
                        organization_id=uuid4(),
                        agent_run_id=agent_run.id,
                        task_id=task.id,
                        query="project.summary",
                    )

                with pytest.raises(KeyError, match="TOOL_DATA_TASK_NOT_FOUND_OR_FORBIDDEN"):
                    await store.query_project(
                        organization_id=ORG_ID,
                        agent_run_id=uuid4(),
                        task_id=task.id,
                        query="project.summary",
                    )

                with pytest.raises(ValueError, match="TOOL_DATA_PROJECT_QUERY_UNSUPPORTED"):
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


def test_tool_data_project_scope_and_query_allowlist() -> None:
    asyncio.run(_acceptance())
