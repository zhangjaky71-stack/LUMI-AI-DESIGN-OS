from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from lumi_api.persistence.models import AgentRun, Approval, Task
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID
from lumi_api.persistence.session import create_engine
from lumi_api.tool_approval_control import ToolApprovalStore

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)


async def _acceptance() -> None:
    engine = create_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    run_id = uuid4()
    task_id = uuid4()
    try:
        async with factory() as session:
            session.add(
                AgentRun(
                    id=run_id,
                    organization_id=ORG_ID,
                    project_id=PROJECT_A_ID,
                    thread_id=f"tool-approval-{run_id}",
                    graph_version="integration-v1",
                    agent_config_version="integration-v1",
                    status="running",
                    budget_json={},
                )
            )
            session.add(
                Task(
                    id=task_id,
                    organization_id=ORG_ID,
                    project_id=PROJECT_A_ID,
                    agent_run_id=run_id,
                    type="publish.external",
                    status="waiting_approval",
                    input_json={},
                    output_json={},
                    metadata_json={},
                    priority=100,
                    attempt_count=0,
                    max_attempts=3,
                    budget_reserved=Decimal("0"),
                    state_version=1,
                    progress_current=0,
                    progress_total=1,
                    dynamic_depth=0,
                    dynamic_child_limit=0,
                )
            )
            await session.commit()

        store = ToolApprovalStore(factory)
        request_hash = "a" * 64
        first = await store.resolve(
            organization_id=ORG_ID,
            agent_run_id=run_id,
            task_id=task_id,
            tool_key="publish.external@1.0.0",
            request_hash=request_hash,
            approval_id=None,
        )
        assert first.decision == "REQUIRED"

        replay_pending = await store.resolve(
            organization_id=ORG_ID,
            agent_run_id=run_id,
            task_id=task_id,
            tool_key="publish.external@1.0.0",
            request_hash=request_hash,
            approval_id=None,
        )
        assert replay_pending.approval_id == first.approval_id

        async with factory() as session:
            approval = await session.get(Approval, first.approval_id)
            assert approval is not None
            approval.status = "approved"
            approval.version += 1
            await session.commit()

        approved = await store.resolve(
            organization_id=ORG_ID,
            agent_run_id=run_id,
            task_id=task_id,
            tool_key="publish.external@1.0.0",
            request_hash=request_hash,
            approval_id=first.approval_id,
        )
        assert approved.decision == "APPROVED"

        wrong_scope = await store.resolve(
            organization_id=ORG_ID,
            agent_run_id=run_id,
            task_id=task_id,
            tool_key="publish.external@1.0.0",
            request_hash="b" * 64,
            approval_id=first.approval_id,
        )
        assert wrong_scope.decision == "DENIED"
        assert wrong_scope.reason_code == "TOOL_APPROVAL_SCOPE_MISMATCH"

        changed_request = await store.resolve(
            organization_id=ORG_ID,
            agent_run_id=run_id,
            task_id=task_id,
            tool_key="publish.external@1.0.0",
            request_hash="b" * 64,
            approval_id=None,
        )
        assert changed_request.decision == "REQUIRED"
        assert changed_request.approval_id != first.approval_id

        async with factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(Approval)
                .where(
                    Approval.organization_id == ORG_ID,
                    Approval.task_id == task_id,
                    Approval.tool_key == "publish.external@1.0.0",
                )
            )
            assert count == 2
    finally:
        await engine.dispose()


def test_tool_approval_durable_postgres_acceptance() -> None:
    asyncio.run(_acceptance())
