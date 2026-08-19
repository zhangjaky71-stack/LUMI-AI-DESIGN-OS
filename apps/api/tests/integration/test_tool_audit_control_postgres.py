from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lumi_api.persistence.models import AuditEvent
from lumi_api.tool_audit_control import (
    CanonicalToolAuditEvent,
    SqlAlchemyToolAuditWriter,
    ToolAuditConflictError,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LUMI_DB_INTEGRATION") != "1",
    reason="set LUMI_DB_INTEGRATION=1 to run PostgreSQL acceptance",
)


def test_canonical_tool_audit_insert_replay_and_conflict() -> None:
    asyncio.run(_scenario())


async def _scenario() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            organization_id = (
                await session.execute(text("SELECT id FROM organizations ORDER BY id LIMIT 1"))
            ).scalar_one_or_none()
        assert organization_id is not None, "db-seed must create at least one organization"

        event_id = uuid4()
        tool_call_id = uuid4()
        event_hash = "a" * 64
        event = CanonicalToolAuditEvent(
            id=event_id,
            organization_id=organization_id,
            actor_type="agent",
            actor_id=None,
            action="tool.invoke.succeeded",
            target_type="tool_call",
            target_id=tool_call_id,
            request_id="trace-postgres-audit",
            metadata_json={
                "schema_version": 1,
                "event_hash": event_hash,
                "actor_id_raw": "agent:design",
                "actor_agent": "design-agent",
                "resolved_tool": "sandbox.execute@1.0.0",
                "risk": "write_internal",
                "purpose": "prove canonical audit persistence",
                "status": "succeeded",
                "arguments": {"api_key": "[REDACTED]"},
                "replayed": False,
                "side_effect_operation_id": str(uuid4()),
                "approval_id": None,
                "error_code": None,
            },
        )
        writer = SqlAlchemyToolAuditWriter(session_factory)

        assert await writer.write(event) is True
        assert await writer.write(event) is False

        conflicting = CanonicalToolAuditEvent(
            id=event.id,
            organization_id=event.organization_id,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            action=event.action,
            target_type=event.target_type,
            target_id=event.target_id,
            request_id=event.request_id,
            metadata_json={**event.metadata_json, "event_hash": "b" * 64},
        )
        with pytest.raises(ToolAuditConflictError):
            await writer.write(conflicting)

        async with session_factory() as session:
            rows = (
                await session.execute(select(AuditEvent).where(AuditEvent.id == event_id))
            ).scalars().all()
        assert len(rows) == 1
        stored = rows[0]
        assert stored.organization_id == organization_id
        assert stored.target_id == tool_call_id
        assert stored.action == "tool.invoke.succeeded"
        assert stored.metadata_json["event_hash"] == event_hash
        assert stored.metadata_json["arguments"]["api_key"] == "[REDACTED]"
    finally:
        await engine.dispose()
