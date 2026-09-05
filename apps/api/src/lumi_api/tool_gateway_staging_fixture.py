from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import (
    AgentRun,
    Artifact,
    Asset,
    AssetRights,
    Organization,
    Project,
    Task,
)
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID, seed
from lumi_api.persistence.session import create_engine, create_session_factory, session_scope

FIXTURE_ID = "node73-tool-gateway-p0-v1"
_FIXTURE_NAMESPACE = UUID("6a2b1e4f-f572-4ed8-b87a-8caf28507ac1")
AGENT_RUN_ID = uuid5(_FIXTURE_NAMESPACE, f"{FIXTURE_ID}:agent-run")
TASK_ID = uuid5(_FIXTURE_NAMESPACE, f"{FIXTURE_ID}:task")
SOURCE_ASSET_ID = uuid5(_FIXTURE_NAMESPACE, f"{FIXTURE_ID}:source-asset")
SOURCE_RIGHTS_ID = uuid5(_FIXTURE_NAMESPACE, f"{FIXTURE_ID}:source-rights")
ARTIFACT_ID = uuid5(_FIXTURE_NAMESPACE, f"{FIXTURE_ID}:artifact")
_MARKER = {"fixture": FIXTURE_ID, "synthetic_only": True}


class StagingFixtureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ToolGatewayStagingFixture:
    schema_version: int
    fixture_id: str
    synthetic_only: bool
    organization_id: str
    project_id: str
    agent_run_id: str
    task_id: str
    source_asset_id: str
    artifact_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mismatch(label: str, field: str, actual: Any, expected: Any) -> StagingFixtureError:
    return StagingFixtureError(
        f"{label} identity collision: {field}={actual!r}, expected {expected!r}"
    )


def _require_fields(label: str, instance: object, expected: dict[str, Any]) -> None:
    for field, value in expected.items():
        actual = getattr(instance, field)
        if actual != value:
            raise _mismatch(label, field, actual, value)


async def _ensure_seed_scope(session: AsyncSession) -> None:
    await seed(session)
    organization = await session.get(Organization, ORG_ID)
    project = await session.get(Project, PROJECT_A_ID)
    if organization is None or project is None:
        raise StagingFixtureError("canonical deterministic seed scope was not materialized")
    _require_fields(
        "organization",
        organization,
        {"id": ORG_ID, "status": "active", "plan": "development"},
    )
    _require_fields(
        "project",
        project,
        {"id": PROJECT_A_ID, "organization_id": ORG_ID, "status": "active"},
    )


async def _ensure_agent_run(session: AsyncSession) -> AgentRun:
    expected = {
        "organization_id": ORG_ID,
        "project_id": PROJECT_A_ID,
        "thread_id": f"{FIXTURE_ID}:thread",
        "graph_version": "staging-p0-v1",
        "agent_config_version": "staging-p0-v1",
        "status": "running",
        "budget_json": {"synthetic_only": True, "fixture": FIXTURE_ID},
    }
    row = await session.get(AgentRun, AGENT_RUN_ID)
    if row is None:
        row = AgentRun(id=AGENT_RUN_ID, **expected)
        session.add(row)
        await session.flush()
    else:
        _require_fields("agent_run", row, expected)
    return row


async def _ensure_task(session: AsyncSession) -> Task:
    expected = {
        "organization_id": ORG_ID,
        "project_id": PROJECT_A_ID,
        "agent_run_id": AGENT_RUN_ID,
        "type": "tool.acceptance",
        "status": "ready",
        "owner_agent_key": "staging-p0-probe",
        "input_json": dict(_MARKER),
        "output_json": {},
        "metadata_json": dict(_MARKER),
        "priority": 100,
        "attempt_count": 0,
        "max_attempts": 3,
        "budget_reserved": Decimal("0"),
    }
    row = await session.get(Task, TASK_ID)
    if row is None:
        row = Task(id=TASK_ID, **expected)
        session.add(row)
        await session.flush()
    else:
        _require_fields("task", row, expected)
    return row


async def _ensure_source_asset(session: AsyncSession) -> Asset:
    expected = {
        "organization_id": ORG_ID,
        "project_id": PROJECT_A_ID,
        "kind": "image",
        "source": "staging-p0-fixture",
        "original_name": "synthetic-tool-gateway-source.png",
        "metadata_json": dict(_MARKER),
        "status": "ready",
        "rejection_code": None,
        "deleted_at": None,
    }
    row = await session.get(Asset, SOURCE_ASSET_ID)
    if row is None:
        row = Asset(id=SOURCE_ASSET_ID, **expected)
        session.add(row)
        await session.flush()
    else:
        _require_fields("source_asset", row, expected)
    return row


async def _ensure_source_rights(session: AsyncSession) -> AssetRights:
    expected = {
        "organization_id": ORG_ID,
        "asset_id": SOURCE_ASSET_ID,
        "scope": "project",
        "source": "synthetic-staging-fixture",
        "attribution_required": False,
        "expires_at": None,
        "policy_json": {
            "fixture": FIXTURE_ID,
            "synthetic_only": True,
            "derived_asset_creation": "allowed",
        },
        "source_type": "GENERATED",
        "owner_assertion": "Synthetic LUMI staging acceptance fixture.",
        "license_type": "OWNED",
        "commercial_use": "ALLOWED",
        "redistribution": "ALLOWED",
        "training_use": "DENIED",
        "source_reference": f"fixture://{FIXTURE_ID}/source-asset",
        "review_status": "VERIFIED",
    }
    row = await session.get(AssetRights, SOURCE_RIGHTS_ID)
    if row is None:
        row = AssetRights(id=SOURCE_RIGHTS_ID, **expected)
        session.add(row)
        await session.flush()
    else:
        _require_fields("source_rights", row, expected)
    return row


async def _ensure_artifact(session: AsyncSession) -> Artifact:
    expected = {
        "organization_id": ORG_ID,
        "project_id": PROJECT_A_ID,
        "kind": "poster",
        "title": "Synthetic Tool Gateway P0 Artifact",
        "metadata_json": dict(_MARKER),
    }
    row = await session.get(Artifact, ARTIFACT_ID)
    if row is None:
        row = Artifact(id=ARTIFACT_ID, **expected)
        session.add(row)
        await session.flush()
    else:
        _require_fields("artifact", row, expected)
    return row


async def materialize(session: AsyncSession) -> ToolGatewayStagingFixture:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:fixture_id, 0))"),
        {"fixture_id": FIXTURE_ID},
    )
    await _ensure_seed_scope(session)
    await _ensure_agent_run(session)
    await _ensure_task(session)
    await _ensure_source_asset(session)
    await _ensure_source_rights(session)
    await _ensure_artifact(session)
    return ToolGatewayStagingFixture(
        schema_version=1,
        fixture_id=FIXTURE_ID,
        synthetic_only=True,
        organization_id=str(ORG_ID),
        project_id=str(PROJECT_A_ID),
        agent_run_id=str(AGENT_RUN_ID),
        task_id=str(TASK_ID),
        source_asset_id=str(SOURCE_ASSET_ID),
        artifact_id=str(ARTIFACT_ID),
    )


async def _main() -> ToolGatewayStagingFixture:
    engine = create_engine()
    factory = create_session_factory(engine)
    try:
        async with session_scope(factory) as session:
            return await materialize(session)
    finally:
        await engine.dispose()


def main() -> int:
    try:
        fixture = asyncio.run(_main())
    except StagingFixtureError as exc:
        raise SystemExit(f"Tool Gateway staging fixture failed: {exc}") from exc
    payload = json.dumps(fixture.to_dict(), sort_keys=True, separators=(",", ":"))
    print(f"LUMI_TOOL_GATEWAY_P0_FIXTURE_JSON={payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
