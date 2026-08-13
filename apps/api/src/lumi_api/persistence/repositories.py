from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from lumi_domain import CostEntry as DomainCostEntry
from lumi_domain import DomainEvent, Money, Project as DomainProject, ProjectStatus
from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from .models import CostLedger, OutboxEvent, Project


class OptimisticLockError(RuntimeError):
    pass


class TenantRepository[ModelT: DeclarativeBase]:
    def __init__(self, session: AsyncSession, organization_id: UUID, model: type[ModelT]) -> None:
        self._session = session
        self.organization_id = organization_id
        self.model = model

    def scoped(self, statement: Select[tuple[ModelT]]) -> Select[tuple[ModelT]]:
        organization_column = getattr(self.model, "organization_id", None)
        if organization_column is None:
            raise TypeError(f"{self.model.__name__} is not tenant scoped")
        return statement.where(organization_column == self.organization_id)

    async def get_model(self, object_id: UUID) -> ModelT | None:
        id_column = getattr(self.model, "id")
        result = await self._session.execute(
            self.scoped(select(self.model)).where(id_column == object_id)
        )
        return result.scalar_one_or_none()


class ProjectRepositoryAdapter(TenantRepository[Project]):
    def __init__(self, session: AsyncSession, organization_id: UUID, actor_id: UUID) -> None:
        super().__init__(session, organization_id, Project)
        self.actor_id = actor_id

    async def get(self, project_id: UUID) -> DomainProject | None:
        row = await self.get_model(project_id)
        if row is None or row.deleted_at is not None:
            return None
        return DomainProject(
            organization_id=row.organization_id,
            workspace_id=row.workspace_id,
            name=row.name,
            id=row.id,
            status=ProjectStatus(row.status),
            brief=dict(row.brief_json),
            brand_id=row.brand_id,
            active_branch_id=row.active_branch_id,
            settings=dict(row.settings_json),
        )

    async def save(self, project: DomainProject) -> None:
        if project.organization_id != self.organization_id:
            raise PermissionError("project organization does not match repository tenant")
        row = await self.get_model(project.id)
        if row is None:
            self._session.add(
                Project(
                    id=project.id,
                    organization_id=project.organization_id,
                    workspace_id=project.workspace_id,
                    name=project.name,
                    status=project.status.value,
                    brief_json=dict(project.brief),
                    brand_id=project.brand_id,
                    active_branch_id=project.active_branch_id,
                    settings_json=dict(project.settings),
                    created_by=self.actor_id,
                )
            )
            await self._session.flush()
            return
        row.name = project.name
        row.status = project.status.value
        row.brief_json = dict(project.brief)
        row.brand_id = project.brand_id
        row.active_branch_id = project.active_branch_id
        row.settings_json = dict(project.settings)
        row.version += 1
        await self._session.flush()

    async def save_with_expected_version(
        self,
        project: DomainProject,
        *,
        expected_version: int,
    ) -> int:
        if project.organization_id != self.organization_id:
            raise PermissionError("project organization does not match repository tenant")
        result = await self._session.execute(
            update(Project)
            .where(
                Project.id == project.id,
                Project.organization_id == self.organization_id,
                Project.version == expected_version,
                Project.deleted_at.is_(None),
            )
            .values(
                name=project.name,
                status=project.status.value,
                brief_json=dict(project.brief),
                brand_id=project.brand_id,
                active_branch_id=project.active_branch_id,
                settings_json=dict(project.settings),
                version=Project.version + 1,
            )
            .returning(Project.version)
        )
        new_version = result.scalar_one_or_none()
        if new_version is None:
            raise OptimisticLockError("project version conflict or tenant mismatch")
        return int(new_version)


class CostLedgerRepositoryAdapter(TenantRepository[CostLedger]):
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        super().__init__(session, organization_id, CostLedger)

    async def append(self, entry: DomainCostEntry) -> None:
        if entry.organization_id != self.organization_id:
            raise PermissionError("cost entry organization does not match repository tenant")
        self._session.add(
            CostLedger(
                id=entry.id,
                organization_id=entry.organization_id,
                reverses_entry_id=entry.reverses_entry_id,
                entry_type=entry.category,
                amount=entry.amount.amount,
                currency=entry.amount.currency,
                occurred_at=entry.recorded_at,
                metadata_json=dict(entry.metadata),
            )
        )
        await self._session.flush()

    async def entries_for_organization(self) -> Sequence[DomainCostEntry]:
        result = await self._session.execute(
            self.scoped(select(CostLedger)).order_by(CostLedger.created_at, CostLedger.id)
        )
        rows = result.scalars().all()
        return tuple(
            DomainCostEntry(
                organization_id=row.organization_id,
                id=row.id,
                amount=Money(row.amount, row.currency),
                category=row.entry_type,
                recorded_at=row.occurred_at,
                reverses_entry_id=row.reverses_entry_id,
                metadata=cast(dict[str, str], dict(row.metadata_json)),
            )
            for row in rows
        )


async def append_outbox_event(session: AsyncSession, event: DomainEvent) -> None:
    payload: dict[str, Any] = dict(event.payload)
    session.add(
        OutboxEvent(
            id=event.event_id,
            organization_id=event.organization_id,
            event_name=event.name,
            aggregate_type="domain",
            aggregate_id=event.aggregate_id,
            payload_json=payload,
        )
    )
    await session.flush()
