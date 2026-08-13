from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from lumi_domain import DomainEvent, Project as DomainProject, ProjectStatus, new_uuid7
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import CostLedger, Organization, Project, User, Workspace
from lumi_api.persistence.repositories import (
    OptimisticLockError,
    ProjectRepositoryAdapter,
    append_outbox_event,
)
from lumi_api.persistence.seed import ORG_ID, USER_OWNER_ID, WORKSPACE_ID
from lumi_api.persistence.session import create_engine

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)


def run(coroutine: object) -> object:
    return asyncio.run(coroutine)  # type: ignore[arg-type]


async def _head_and_table_count() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            head = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            assert head == "0003_runtime_privilege_hardening"
            count = (
                await connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_type = 'BASE TABLE'
                          AND table_name <> 'alembic_version'
                        """
                    )
                )
            ).scalar_one()
            assert count == 41
    finally:
        await engine.dispose()


def test_empty_database_upgrades_to_expected_head_and_table_count() -> None:
    run(_head_and_table_count())


async def _tenant_scope_and_optimistic_lock() -> None:
    engine = create_engine()
    tenant_b = new_uuid7()
    workspace_b = new_uuid7()
    project_b = new_uuid7()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                session.add(
                    Organization(
                        id=tenant_b,
                        name="Tenant B",
                        slug=f"tenant-b-{str(tenant_b)[-8:]}",
                        status="active",
                        plan="test",
                        settings_json={},
                    )
                )
                session.add(
                    Workspace(
                        id=workspace_b,
                        organization_id=tenant_b,
                        name="Tenant B Workspace",
                        slug="test",
                        settings_json={},
                    )
                )
                session.add(
                    Project(
                        id=project_b,
                        organization_id=tenant_b,
                        workspace_id=workspace_b,
                        name="Tenant B Secret Project",
                        status="active",
                        brief_json={},
                        settings_json={},
                        created_by=USER_OWNER_ID,
                    )
                )
                await session.flush()

                tenant_a_repository = ProjectRepositoryAdapter(session, ORG_ID, USER_OWNER_ID)
                assert await tenant_a_repository.get(project_b) is None

                project_a_id = new_uuid7()
                domain_project = DomainProject(
                    organization_id=ORG_ID,
                    workspace_id=WORKSPACE_ID,
                    name="Optimistic Lock Fixture",
                    id=project_a_id,
                    status=ProjectStatus.ACTIVE,
                )
                await tenant_a_repository.save(domain_project)
                stored = await session.scalar(
                    select(Project).where(Project.id == project_a_id, Project.organization_id == ORG_ID)
                )
                assert stored is not None
                expected = stored.version
                domain_project.name = "Updated Once"
                new_version = await tenant_a_repository.save_with_expected_version(
                    domain_project,
                    expected_version=expected,
                )
                assert new_version == expected + 1
                with pytest.raises(OptimisticLockError):
                    await tenant_a_repository.save_with_expected_version(
                        domain_project,
                        expected_version=expected,
                    )
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_tenant_scope_and_optimistic_lock() -> None:
    run(_tenant_scope_and_optimistic_lock())


async def _decimal_and_immutable_ledger() -> None:
    engine = create_engine()
    entry_id = new_uuid7()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                session.add(
                    CostLedger(
                        id=entry_id,
                        organization_id=ORG_ID,
                        entry_type="provider_cost",
                        amount=Decimal("0.12345678"),
                        currency="USD",
                        quantity=Decimal("1234567890.1234567890"),
                        unit="tokens",
                        occurred_at=datetime.now(UTC),
                        metadata_json={"fixture": "precision"},
                    )
                )
                await session.flush()
                row = await session.scalar(select(CostLedger).where(CostLedger.id == entry_id))
                assert row is not None
                assert row.amount == Decimal("0.12345678")
                assert row.quantity == Decimal("1234567890.1234567890")

                with pytest.raises(DBAPIError):
                    await session.execute(
                        update(CostLedger)
                        .where(CostLedger.id == entry_id)
                        .values(amount=Decimal("9.00000000"))
                    )
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_decimal_precision_and_ledger_db_immutability() -> None:
    run(_decimal_and_immutable_ledger())


async def _outbox_atomicity() -> None:
    engine = create_engine()
    project_id = new_uuid7()
    event_id = new_uuid7()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                project = DomainProject(
                    organization_id=ORG_ID,
                    workspace_id=WORKSPACE_ID,
                    name="Outbox Rollback Fixture",
                    id=project_id,
                )
                repository = ProjectRepositoryAdapter(session, ORG_ID, USER_OWNER_ID)
                await repository.save(project)
                await append_outbox_event(
                    session,
                    DomainEvent(
                        name="project.created",
                        organization_id=ORG_ID,
                        aggregate_id=project_id,
                        event_id=event_id,
                        payload={"name": project.name},
                    ),
                )
            finally:
                await session.close()
                await transaction.rollback()

        async with engine.connect() as verification:
            project_count = (
                await verification.execute(
                    text("SELECT count(*) FROM projects WHERE id = :id"),
                    {"id": project_id},
                )
            ).scalar_one()
            event_count = (
                await verification.execute(
                    text("SELECT count(*) FROM outbox_events WHERE id = :id"),
                    {"id": event_id},
                )
            ).scalar_one()
            assert project_count == 0
            assert event_count == 0
    finally:
        await engine.dispose()


def test_business_write_and_outbox_share_transaction() -> None:
    run(_outbox_atomicity())
