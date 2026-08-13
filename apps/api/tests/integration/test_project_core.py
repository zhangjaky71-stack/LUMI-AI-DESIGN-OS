from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest
from lumi_domain import new_uuid7
from lumi_project_core import ProjectListFilter
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import (
    Asset,
    AuditEvent,
    Organization,
    OutboxEvent,
    Project,
    ProjectBriefVersion,
    ProjectSummary,
    Workspace,
)
from lumi_api.persistence.seed import ORG_ID, USER_OWNER_ID, WORKSPACE_ID
from lumi_api.persistence.session import create_engine
from lumi_api.projects.errors import ProjectConflict, ProjectNotFound
from lumi_api.projects.service import ProjectService

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)

T = TypeVar("T")


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def brief(label: str = "v1") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "objective": f"Project Core integration {label}",
        "audience": ["design team"],
        "brand_context": "Keep the approved brand identity.",
        "deliverables": [{"key": "poster", "kind": "poster", "quantity": 1}],
        "channels": ["social"],
        "visual_direction": ["minimal"],
        "copy_requirements": ["concise"],
        "constraint_ids": ["constraint:keep-logo"],
        "reference_asset_ids": [],
        "locale": "en",
        "notes": label,
    }


def settings() -> dict[str, object]:
    return {
        "default_locale": "en",
        "timezone": "UTC",
        "cost_budget_default": "25",
        "quality_profile": "balanced",
        "model_policy_id": None,
        "data_retention_profile": "standard",
    }


async def _create_transaction_idempotency_and_brief_history() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                service = ProjectService(session)
                project = await service.create_project(
                    organization_id=ORG_ID,
                    actor_id=USER_OWNER_ID,
                    request_id="project-create-integration",
                    idempotency_key="project-create-integration-0001",
                    workspace_id=WORKSPACE_ID,
                    name="Project Core Fixture",
                    brief=brief(),
                    brand_id=None,
                    settings=settings(),
                )
                await session.flush()
                assert project.brief_version == 1
                assert project.status == "draft"

                history_count = await session.scalar(
                    select(func.count()).select_from(ProjectBriefVersion).where(
                        ProjectBriefVersion.project_id == project.id
                    )
                )
                summary_count = await session.scalar(
                    select(func.count()).select_from(ProjectSummary).where(
                        ProjectSummary.project_id == project.id
                    )
                )
                outbox = await session.scalar(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == project.id,
                        OutboxEvent.event_name == "project.created",
                    )
                )
                audit = await session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.target_id == project.id,
                        AuditEvent.action == "project.created",
                    )
                )
                assert history_count == 1
                assert summary_count == 1
                assert outbox is not None
                assert audit is not None

                retry = await service.create_project(
                    organization_id=ORG_ID,
                    actor_id=USER_OWNER_ID,
                    request_id="project-create-retry",
                    idempotency_key="project-create-integration-0001",
                    workspace_id=WORKSPACE_ID,
                    name="Project Core Fixture",
                    brief=brief(),
                    brand_id=None,
                    settings=settings(),
                )
                assert retry.id == project.id

                with pytest.raises(ProjectConflict, match="idempotency key"):
                    await service.create_project(
                        organization_id=ORG_ID,
                        actor_id=USER_OWNER_ID,
                        request_id="project-create-reused",
                        idempotency_key="project-create-integration-0001",
                        workspace_id=WORKSPACE_ID,
                        name="Different payload",
                        brief=brief(),
                        brand_id=None,
                        settings=settings(),
                    )
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_create_transaction_idempotency_and_brief_history() -> None:
    run(_create_transaction_idempotency_and_brief_history())


async def _brief_version_concurrency_archive_restore_and_asset_safety() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                service = ProjectService(session)
                project = await service.create_project(
                    organization_id=ORG_ID,
                    actor_id=USER_OWNER_ID,
                    request_id="project-lifecycle",
                    idempotency_key="project-lifecycle-integration-0001",
                    workspace_id=WORKSPACE_ID,
                    name="Lifecycle Fixture",
                    brief=brief("v1"),
                    brand_id=None,
                    settings=settings(),
                )
                version = project.version
                updated = await service.update_project(
                    organization_id=ORG_ID,
                    actor_id=USER_OWNER_ID,
                    request_id="project-brief-v2",
                    project_id=project.id,
                    expected_version=version,
                    changes={"brief": brief("v2")},
                )
                assert updated.brief_version == 2
                assert updated.version == version + 1
                versions = await service.list_brief_versions(
                    organization_id=ORG_ID, project_id=project.id
                )
                assert [item.brief_version for item in versions] == [2, 1]

                no_change = await service.update_project(
                    organization_id=ORG_ID,
                    actor_id=USER_OWNER_ID,
                    request_id="project-brief-same",
                    project_id=project.id,
                    expected_version=updated.version,
                    changes={"brief": brief("v2")},
                )
                assert no_change.version == updated.version
                assert no_change.brief_version == 2

                with pytest.raises(ProjectConflict, match="PROJECT_VERSION_CONFLICT"):
                    await service.update_project(
                        organization_id=ORG_ID,
                        actor_id=USER_OWNER_ID,
                        request_id="project-stale",
                        project_id=project.id,
                        expected_version=1,
                        changes={"name": "stale"},
                    )

                active = await service.update_project(
                    organization_id=ORG_ID,
                    actor_id=USER_OWNER_ID,
                    request_id="project-active",
                    project_id=project.id,
                    expected_version=no_change.version,
                    changes={"status": "active"},
                )
                await service.require_paid_command_allowed(
                    organization_id=ORG_ID, project_id=project.id
                )

                asset = Asset(
                    id=new_uuid7(),
                    organization_id=ORG_ID,
                    project_id=project.id,
                    kind="image",
                    source="integration",
                    original_name="protected-product.png",
                    metadata_json={},
                )
                session.add(asset)
                await session.flush()

                archived = await service.archive_project(
                    organization_id=ORG_ID,
                    actor_id=USER_OWNER_ID,
                    request_id="project-archive",
                    project_id=project.id,
                    expected_version=active.version,
                )
                assert archived.status == "archived"
                with pytest.raises(ProjectConflict, match="PROJECT_NOT_ACTIVE"):
                    await service.require_paid_command_allowed(
                        organization_id=ORG_ID, project_id=project.id
                    )
                stored_asset = await session.scalar(select(Asset).where(Asset.id == asset.id))
                assert stored_asset is not None
                assert stored_asset.deleted_at is None

                restored = await service.restore_project(
                    organization_id=ORG_ID,
                    actor_id=USER_OWNER_ID,
                    request_id="project-restore",
                    project_id=project.id,
                    expected_version=archived.version,
                )
                assert restored.status == "paused"
                with pytest.raises(ProjectConflict, match="PROJECT_NOT_ACTIVE"):
                    await service.require_paid_command_allowed(
                        organization_id=ORG_ID, project_id=project.id
                    )
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_brief_version_concurrency_archive_restore_and_asset_safety() -> None:
    run(_brief_version_concurrency_archive_restore_and_asset_safety())


async def _tenant_isolation_cursor_and_history_db_immutability() -> None:
    engine = create_engine()
    tenant_b = new_uuid7()
    workspace_b = new_uuid7()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                session.add(
                    Organization(
                        id=tenant_b,
                        name="Project Tenant B",
                        slug=f"project-tenant-b-{str(tenant_b)[-8:]}",
                        status="active",
                        plan="test",
                        settings_json={},
                    )
                )
                session.add(
                    Workspace(
                        id=workspace_b,
                        organization_id=tenant_b,
                        name="Project Tenant B Workspace",
                        slug="project-core",
                        settings_json={},
                    )
                )
                await session.flush()
                service = ProjectService(session)
                tenant_b_project = await service.create_project(
                    organization_id=tenant_b,
                    actor_id=USER_OWNER_ID,
                    request_id="tenant-b-project",
                    idempotency_key="tenant-b-project-integration-0001",
                    workspace_id=workspace_b,
                    name="Tenant B Secret",
                    brief=brief("tenant-b"),
                    brand_id=None,
                    settings=settings(),
                )
                with pytest.raises(ProjectNotFound):
                    await service.get_project(
                        organization_id=ORG_ID, project_id=tenant_b_project.id
                    )

                created: list[Project] = []
                for index in range(3):
                    created.append(
                        await service.create_project(
                            organization_id=ORG_ID,
                            actor_id=USER_OWNER_ID,
                            request_id=f"cursor-{index}",
                            idempotency_key=f"cursor-project-integration-{index:04d}",
                            workspace_id=WORKSPACE_ID,
                            name=f"Cursor Fixture {index}",
                            brief=brief(f"cursor-{index}"),
                            brand_id=None,
                            settings=settings(),
                        )
                    )
                first, cursor, has_more = await service.list_projects(
                    organization_id=ORG_ID,
                    filters=ProjectListFilter(name_query="Cursor Fixture"),
                    cursor=None,
                    limit=2,
                )
                assert has_more and cursor is not None and len(first) == 2
                second, _, _ = await service.list_projects(
                    organization_id=ORG_ID,
                    filters=ProjectListFilter(name_query="Cursor Fixture"),
                    cursor=cursor,
                    limit=2,
                )
                assert {item.id for item in first}.isdisjoint({item.id for item in second})
                assert {item.id for item in first + second} == {item.id for item in created}

                history = await session.scalar(
                    select(ProjectBriefVersion).where(
                        ProjectBriefVersion.project_id == created[0].id,
                        ProjectBriefVersion.brief_version == 1,
                    )
                )
                assert history is not None
                nested = await session.begin_nested()
                try:
                    with pytest.raises(DBAPIError):
                        await session.execute(
                            update(ProjectBriefVersion)
                            .where(ProjectBriefVersion.id == history.id)
                            .values(brief_hash="0" * 64)
                        )
                        await session.flush()
                finally:
                    await nested.rollback()
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_tenant_isolation_cursor_and_history_db_immutability() -> None:
    run(_tenant_isolation_cursor_and_history_db_immutability())
