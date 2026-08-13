from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Artifact,
    ArtifactBranch,
    ArtifactEdge,
    ArtifactVersion,
    Asset,
    AssetFile,
    AssetRights,
    Brand,
    DesignDocument,
    Organization,
    OrganizationMember,
    Project,
    Task,
    TaskDependency,
    User,
    Workspace,
)
from .session import create_engine, create_session_factory, session_scope

ORG_ID = UUID("01900000-0000-7000-8000-000000000001")
USER_OWNER_ID = UUID("01900000-0000-7000-8000-000000000002")
USER_MEMBER_ID = UUID("01900000-0000-7000-8000-000000000003")
WORKSPACE_ID = UUID("01900000-0000-7000-8000-000000000004")
BRAND_ID = UUID("01900000-0000-7000-8000-000000000005")
PROJECT_A_ID = UUID("01900000-0000-7000-8000-000000000006")
PROJECT_B_ID = UUID("01900000-0000-7000-8000-000000000007")
ASSET_ID = UUID("01900000-0000-7000-8000-000000000008")
ASSET_FILE_ID = UUID("01900000-0000-7000-8000-000000000009")
ASSET_RIGHTS_ID = UUID("01900000-0000-7000-8000-00000000000a")
DOCUMENT_ID = UUID("01900000-0000-7000-8000-00000000000b")
ARTIFACT_ID = UUID("01900000-0000-7000-8000-00000000000c")
BRANCH_ID = UUID("01900000-0000-7000-8000-00000000000d")
VERSION_1_ID = UUID("01900000-0000-7000-8000-00000000000e")
VERSION_2_ID = UUID("01900000-0000-7000-8000-00000000000f")
EDGE_ID = UUID("01900000-0000-7000-8000-000000000010")
TASK_RESEARCH_ID = UUID("01900000-0000-7000-8000-000000000011")
TASK_DESIGN_ID = UUID("01900000-0000-7000-8000-000000000012")
TASK_DEP_ID = UUID("01900000-0000-7000-8000-000000000013")


async def _insert_ignore(session: AsyncSession, model: type[object], values: dict[str, object]) -> None:
    table = getattr(model, "__table__")
    await session.execute(insert(table).values(**values).on_conflict_do_nothing(index_elements=["id"]))


async def seed(session: AsyncSession) -> None:
    await _insert_ignore(
        session,
        User,
        {
            "id": USER_OWNER_ID,
            "email": "owner@lumi.local",
            "display_name": "LUMI Owner",
            "status": "active",
        },
    )
    await _insert_ignore(
        session,
        User,
        {
            "id": USER_MEMBER_ID,
            "email": "designer@lumi.local",
            "display_name": "LUMI Designer",
            "status": "active",
        },
    )
    await _insert_ignore(
        session,
        Organization,
        {
            "id": ORG_ID,
            "name": "LUMI Demo Organization",
            "slug": "lumi-demo",
            "status": "active",
            "plan": "development",
            "settings_json": {},
        },
    )
    await _insert_ignore(
        session,
        OrganizationMember,
        {
            "id": UUID("01900000-0000-7000-8000-000000000014"),
            "organization_id": ORG_ID,
            "user_id": USER_OWNER_ID,
            "role": "owner",
            "status": "active",
        },
    )
    await _insert_ignore(
        session,
        OrganizationMember,
        {
            "id": UUID("01900000-0000-7000-8000-000000000015"),
            "organization_id": ORG_ID,
            "user_id": USER_MEMBER_ID,
            "role": "designer",
            "status": "active",
        },
    )
    await _insert_ignore(
        session,
        Workspace,
        {
            "id": WORKSPACE_ID,
            "organization_id": ORG_ID,
            "name": "Demo Workspace",
            "slug": "demo",
            "settings_json": {},
        },
    )
    await _insert_ignore(
        session,
        Brand,
        {
            "id": BRAND_ID,
            "organization_id": ORG_ID,
            "name": "LUMI Seed Brand",
            "profile_json": {"industry": "food_and_beverage"},
            "tone_json": ["minimal", "premium"],
        },
    )
    for project_id, name in (
        (PROJECT_A_ID, "Seed Project A"),
        (PROJECT_B_ID, "Seed Project B"),
    ):
        await _insert_ignore(
            session,
            Project,
            {
                "id": project_id,
                "organization_id": ORG_ID,
                "workspace_id": WORKSPACE_ID,
                "name": name,
                "status": "active",
                "brief_json": {"goal": "deterministic NODE-10 fixture"},
                "brand_id": BRAND_ID,
                "settings_json": {},
                "created_by": USER_OWNER_ID,
            },
        )
    await _insert_ignore(
        session,
        Asset,
        {
            "id": ASSET_ID,
            "organization_id": ORG_ID,
            "project_id": PROJECT_A_ID,
            "kind": "image",
            "source": "seed",
            "original_name": "sample-product.png",
            "metadata_json": {"fixture": True},
        },
    )
    await _insert_ignore(
        session,
        AssetFile,
        {
            "id": ASSET_FILE_ID,
            "organization_id": ORG_ID,
            "asset_id": ASSET_ID,
            "variant": "original",
            "bucket": "lumi-assets",
            "object_key": "seed/sample-product.png",
            "checksum_sha256": "0" * 64,
            "mime_type": "image/png",
            "byte_size": 0,
        },
    )
    await _insert_ignore(
        session,
        AssetRights,
        {
            "id": ASSET_RIGHTS_ID,
            "organization_id": ORG_ID,
            "asset_id": ASSET_ID,
            "scope": "internal",
            "source": "deterministic-seed",
            "attribution_required": False,
            "policy_json": {"fixture_only": True},
        },
    )
    await _insert_ignore(
        session,
        DesignDocument,
        {
            "id": DOCUMENT_ID,
            "organization_id": ORG_ID,
            "project_id": PROJECT_A_ID,
            "title": "Seed Design Document",
            "design_ir_version": "1",
        },
    )
    await _insert_ignore(
        session,
        Artifact,
        {
            "id": ARTIFACT_ID,
            "organization_id": ORG_ID,
            "project_id": PROJECT_A_ID,
            "kind": "poster",
            "title": "Seed Poster",
            "metadata_json": {},
        },
    )
    await _insert_ignore(
        session,
        ArtifactBranch,
        {
            "id": BRANCH_ID,
            "organization_id": ORG_ID,
            "project_id": PROJECT_A_ID,
            "artifact_id": ARTIFACT_ID,
            "name": "main",
            "head_version_id": VERSION_2_ID,
        },
    )
    await _insert_ignore(
        session,
        ArtifactVersion,
        {
            "id": VERSION_1_ID,
            "organization_id": ORG_ID,
            "project_id": PROJECT_A_ID,
            "artifact_id": ARTIFACT_ID,
            "branch_id": BRANCH_ID,
            "version_number": 1,
            "status": "ready",
            "content_hash": "sha256:seed-v1",
            "metadata_json": {},
            "created_by_type": "user",
            "created_by_id": USER_OWNER_ID,
        },
    )
    await _insert_ignore(
        session,
        ArtifactVersion,
        {
            "id": VERSION_2_ID,
            "organization_id": ORG_ID,
            "project_id": PROJECT_A_ID,
            "artifact_id": ARTIFACT_ID,
            "branch_id": BRANCH_ID,
            "parent_version_id": VERSION_1_ID,
            "version_number": 2,
            "status": "ready",
            "content_hash": "sha256:seed-v2",
            "metadata_json": {},
            "created_by_type": "agent",
        },
    )
    await _insert_ignore(
        session,
        ArtifactEdge,
        {
            "id": EDGE_ID,
            "organization_id": ORG_ID,
            "from_artifact_version_id": VERSION_1_ID,
            "to_artifact_version_id": VERSION_2_ID,
            "edge_type": "EDITED_FROM",
            "metadata_json": {},
        },
    )
    await _insert_ignore(
        session,
        Task,
        {
            "id": TASK_RESEARCH_ID,
            "organization_id": ORG_ID,
            "project_id": PROJECT_A_ID,
            "type": "research",
            "status": "succeeded",
            "input_json": {},
            "output_json": {"fixture": True},
            "priority": 100,
            "attempt_count": 1,
            "max_attempts": 3,
            "budget_reserved": 0,
        },
    )
    await _insert_ignore(
        session,
        Task,
        {
            "id": TASK_DESIGN_ID,
            "organization_id": ORG_ID,
            "project_id": PROJECT_A_ID,
            "type": "design",
            "status": "ready",
            "input_json": {},
            "output_json": {},
            "priority": 100,
            "attempt_count": 0,
            "max_attempts": 3,
            "budget_reserved": 0,
        },
    )
    await _insert_ignore(
        session,
        TaskDependency,
        {
            "id": TASK_DEP_ID,
            "organization_id": ORG_ID,
            "task_id": TASK_DESIGN_ID,
            "depends_on_task_id": TASK_RESEARCH_ID,
        },
    )


async def main() -> None:
    engine = create_engine()
    factory = create_session_factory(engine)
    try:
        async with session_scope(factory) as session:
            await seed(session)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
