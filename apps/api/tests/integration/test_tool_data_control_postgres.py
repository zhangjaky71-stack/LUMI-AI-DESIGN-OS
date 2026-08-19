from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from lumi_api.persistence.models import AgentRun, Artifact, Asset, AssetRights, Task
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


async def _derived_count(factory: async_sessionmaker) -> int:
    async with factory() as session:
        rows = (
            await session.scalars(
                select(Asset.id).where(
                    Asset.organization_id == ORG_ID,
                    Asset.project_id == PROJECT_A_ID,
                    Asset.source == "derived",
                    Asset.deleted_at.is_(None),
                )
            )
        ).all()
        return len(rows)


async def _acceptance() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            factory = async_sessionmaker(bind=connection, expire_on_commit=False)
            try:
                async with factory.begin() as setup:
                    agent_run = AgentRun(
                        organization_id=ORG_ID,
                        project_id=PROJECT_A_ID,
                        thread_id=f"tool-data-{uuid4()}",
                        graph_version="tool-data-test-v1",
                        agent_config_version="tool-data-test-v1",
                        status="running",
                        budget_json={},
                    )
                    setup.add(agent_run)
                    await setup.flush()

                    task = Task(
                        organization_id=ORG_ID,
                        project_id=PROJECT_A_ID,
                        agent_run_id=agent_run.id,
                        type="asset.write-derived",
                        status="running",
                        input_json={},
                        output_json={},
                        metadata_json={},
                        priority=100,
                        attempt_count=0,
                        max_attempts=3,
                        budget_reserved=Decimal("0"),
                    )
                    source_asset = Asset(
                        organization_id=ORG_ID,
                        project_id=PROJECT_A_ID,
                        kind="image",
                        source="tool-data-test",
                        original_name="source.png",
                        metadata_json={"origin": "acceptance"},
                        status="ready",
                    )
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
                    setup.add_all([task, source_asset, foreign_asset, foreign_artifact])
                    await setup.flush()
                    source_rights = AssetRights(
                        organization_id=ORG_ID,
                        asset_id=source_asset.id,
                        scope="project",
                        source="acceptance-user",
                        attribution_required=True,
                        policy_json={"derived": "allowed"},
                        source_type="USER_UPLOAD",
                        owner_assertion="owned by acceptance user",
                        license_type="OWNED",
                        commercial_use="ALLOWED",
                        redistribution="DENIED",
                        training_use="DENIED",
                        source_reference="acceptance://source",
                        review_status="ASSERTED",
                    )
                    setup.add(source_rights)
                    await setup.flush()

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

                tool_call_id = uuid4()
                derived = await store.write_derived_asset(
                    organization_id=ORG_ID,
                    agent_run_id=agent_run.id,
                    task_id=task.id,
                    tool_call_id=tool_call_id,
                    source_asset_id=source_asset.id,
                    artifact_ref=f"artifact://{ARTIFACT_ID}",
                    metadata={"variant": "social", "derived_by": "caller-spoof"},
                )
                derived_id = UUID(derived["asset_id"])
                assert derived["project_id"] == str(PROJECT_A_ID)
                assert derived["source"] == "derived"
                assert derived["status"] == "ready"
                assert derived["metadata"]["variant"] == "social"
                assert derived["metadata"]["source_asset_id"] == str(source_asset.id)
                assert derived["metadata"]["artifact_ref"] == f"artifact://{ARTIFACT_ID}"
                assert derived["metadata"]["tool_call_id"] == str(tool_call_id)
                assert derived["metadata"]["derived_by"] == "tool:asset.write-derived:1.0.0"

                async with factory() as verify:
                    cloned_rights = await verify.scalar(
                        select(AssetRights).where(
                            AssetRights.organization_id == ORG_ID,
                            AssetRights.asset_id == derived_id,
                        )
                    )
                    assert cloned_rights is not None
                    assert cloned_rights.scope == source_rights.scope
                    assert cloned_rights.source == source_rights.source
                    assert cloned_rights.attribution_required is True
                    assert cloned_rights.policy_json == source_rights.policy_json
                    assert cloned_rights.source_type == source_rights.source_type
                    assert cloned_rights.license_type == source_rights.license_type
                    assert cloned_rights.commercial_use == source_rights.commercial_use
                    assert cloned_rights.redistribution == source_rights.redistribution
                    assert cloned_rights.training_use == source_rights.training_use
                    assert cloned_rights.review_status == source_rights.review_status

                before_invalid = await _derived_count(factory)
                with pytest.raises(
                    KeyError,
                    match="TOOL_DATA_ARTIFACT_NOT_FOUND_OR_FORBIDDEN",
                ):
                    await store.write_derived_asset(
                        organization_id=ORG_ID,
                        agent_run_id=agent_run.id,
                        task_id=task.id,
                        tool_call_id=uuid4(),
                        source_asset_id=source_asset.id,
                        artifact_ref=f"artifact://{foreign_artifact.id}",
                        metadata={},
                    )
                assert await _derived_count(factory) == before_invalid

                with pytest.raises(ValueError, match="TOOL_DATA_ARTIFACT_REF_INVALID"):
                    await store.write_derived_asset(
                        organization_id=ORG_ID,
                        agent_run_id=agent_run.id,
                        task_id=task.id,
                        tool_call_id=uuid4(),
                        source_asset_id=source_asset.id,
                        artifact_ref="https://example.com/not-canonical",
                        metadata={},
                    )

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
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_tool_data_project_asset_artifact_scope_and_derived_write() -> None:
    asyncio.run(_acceptance())
