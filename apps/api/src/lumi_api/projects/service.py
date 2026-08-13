from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lumi_domain import InvalidTransition, Project as DomainProject, ProjectStatus, new_uuid7
from lumi_project_core import (
    BriefValidationError,
    ProjectCursor,
    ProjectListFilter,
    ProjectSettingsError,
    brief_hash,
    decode_cursor,
    encode_cursor,
    normalize_brief,
    normalize_project_settings,
    require_paid_command_allowed,
    restore,
)
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import (
    ArtifactBranch,
    AuditEvent,
    Brand,
    IdempotencyOperation,
    OutboxEvent,
    Project,
    ProjectBriefVersion,
    ProjectSummary,
    Workspace,
)

from .errors import ProjectConflict, ProjectInvalid, ProjectNotFound


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_projects(
        self,
        *,
        organization_id: UUID,
        filters: ProjectListFilter,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Project], str | None, bool]:
        if not 1 <= limit <= 100:
            raise ProjectInvalid("INVALID_PAGE_LIMIT", "project page limit is invalid")
        statement = select(Project).where(
            Project.organization_id == organization_id,
            Project.deleted_at.is_(None),
        )
        if filters.status is not None:
            statement = statement.where(Project.status == filters.status.lower())
        if filters.workspace_id is not None:
            try:
                workspace_id = UUID(filters.workspace_id)
            except ValueError as exc:
                raise ProjectInvalid("INVALID_WORKSPACE_ID") from exc
            statement = statement.where(Project.workspace_id == workspace_id)
        if filters.created_by is not None:
            try:
                created_by = UUID(filters.created_by)
            except ValueError as exc:
                raise ProjectInvalid("INVALID_CREATED_BY") from exc
            statement = statement.where(Project.created_by == created_by)
        if filters.updated_after is not None:
            statement = statement.where(Project.updated_at >= filters.updated_after)
        if filters.updated_before is not None:
            statement = statement.where(Project.updated_at <= filters.updated_before)
        if filters.name_query is not None:
            statement = statement.where(Project.name.ilike(f"%{filters.name_query.strip()}%"))

        if cursor is not None:
            try:
                decoded = decode_cursor(cursor)
                cursor_id = UUID(decoded.project_id)
            except (ValueError, TypeError) as exc:
                raise ProjectInvalid("INVALID_CURSOR", "project cursor is invalid") from exc
            statement = statement.where(
                or_(
                    Project.created_at < decoded.created_at,
                    and_(Project.created_at == decoded.created_at, Project.id < cursor_id),
                )
            )

        rows = (
            await self.session.scalars(
                statement.order_by(Project.created_at.desc(), Project.id.desc()).limit(limit + 1)
            )
        ).all()
        has_more = len(rows) > limit
        items = list(rows[:limit])
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(
                ProjectCursor(created_at=last.created_at, project_id=str(last.id))
            )
        return items, next_cursor, has_more

    async def create_project(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
        workspace_id: UUID,
        name: str,
        brief: Mapping[str, Any] | None,
        brand_id: UUID | None,
        settings: Mapping[str, Any] | None,
        source_input: str | None = None,
    ) -> Project:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 300:
            raise ProjectInvalid("INVALID_PROJECT_NAME")
        normalized_brief = self._normalize_brief(brief)
        normalized_settings = self._normalize_settings(settings)
        await self._require_workspace(organization_id, workspace_id)
        await self._require_brand(organization_id, brand_id)

        request_hash = self._create_request_hash(
            workspace_id=workspace_id,
            name=normalized_name,
            brief=normalized_brief,
            brand_id=brand_id,
            settings=normalized_settings,
        )
        existing = await self.session.scalar(
            select(IdempotencyOperation).where(
                IdempotencyOperation.organization_id == organization_id,
                IdempotencyOperation.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.operation_type != "project.create" or existing.request_hash != request_hash:
                raise ProjectConflict(
                    "IDEMPOTENCY_KEY_REUSED",
                    "idempotency key was already used for a different request",
                )
            if existing.status == "completed" and existing.result_ref:
                try:
                    project_id = UUID(existing.result_ref)
                except ValueError as exc:
                    raise ProjectConflict("IDEMPOTENCY_RESULT_INVALID") from exc
                row = await self._get_project_row(organization_id, project_id)
                if row is None:
                    raise ProjectConflict("IDEMPOTENCY_RESULT_MISSING")
                return row
            raise ProjectConflict("IDEMPOTENT_OPERATION_IN_PROGRESS")

        operation = IdempotencyOperation(
            id=new_uuid7(),
            organization_id=organization_id,
            idempotency_key=idempotency_key,
            operation_type="project.create",
            status="pending",
            request_hash=request_hash,
        )
        project = Project(
            id=new_uuid7(),
            organization_id=organization_id,
            workspace_id=workspace_id,
            name=normalized_name,
            status=ProjectStatus.DRAFT.value,
            brief_json=normalized_brief,
            brief_version=1,
            brand_id=brand_id,
            settings_json=normalized_settings,
            created_by=actor_id,
        )
        self.session.add_all([operation, project])
        await self.session.flush()

        self.session.add(
            ProjectBriefVersion(
                id=new_uuid7(),
                organization_id=organization_id,
                project_id=project.id,
                brief_version=1,
                brief_hash=brief_hash(normalized_brief),
                brief_json=normalized_brief,
                source_input=source_input,
                created_by=actor_id,
            )
        )
        self.session.add(
            ProjectSummary(
                id=new_uuid7(),
                organization_id=organization_id,
                project_id=project.id,
                last_activity_at=datetime.now(UTC),
                active_run_count=0,
                artifact_count=0,
            )
        )
        self._append_event(
            organization_id=organization_id,
            project_id=project.id,
            name="project.created",
            payload={"workspace_id": str(workspace_id), "brief_version": 1},
        )
        self._append_audit(
            organization_id=organization_id,
            actor_id=actor_id,
            request_id=request_id,
            project_id=project.id,
            action="project.created",
            metadata={"workspace_id": str(workspace_id)},
        )
        operation.status = "completed"
        operation.result_ref = str(project.id)
        await self.session.flush()
        return project

    async def get_project(self, *, organization_id: UUID, project_id: UUID) -> Project:
        row = await self._get_project_row(organization_id, project_id)
        if row is None:
            raise ProjectNotFound()
        return row

    async def update_project(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        project_id: UUID,
        expected_version: int,
        changes: Mapping[str, Any],
        source_input: str | None = None,
    ) -> Project:
        row = await self._get_project_row(organization_id, project_id)
        if row is None:
            raise ProjectNotFound()
        if row.version != expected_version:
            raise ProjectConflict("PROJECT_VERSION_CONFLICT")
        if row.status == ProjectStatus.ARCHIVED.value:
            raise ProjectConflict("PROJECT_ARCHIVED", "restore an archived project before editing")

        values: dict[str, Any] = {}
        events: list[tuple[str, dict[str, Any]]] = []
        brief_history: tuple[int, dict[str, Any], str] | None = None

        if "name" in changes and changes["name"] is not None:
            name = str(changes["name"]).strip()
            if not name or len(name) > 300:
                raise ProjectInvalid("INVALID_PROJECT_NAME")
            if name != row.name:
                values["name"] = name

        if "status" in changes and changes["status"] is not None:
            target = changes["status"]
            target_status = target if isinstance(target, ProjectStatus) else ProjectStatus(str(target))
            if target_status != ProjectStatus(row.status):
                domain = self._to_domain(row)
                try:
                    domain.transition_to(target_status)
                except InvalidTransition as exc:
                    raise ProjectConflict("INVALID_PROJECT_STATUS_TRANSITION", str(exc)) from exc
                values["status"] = target_status.value
                event_name = {
                    ProjectStatus.PAUSED: "project.paused",
                    ProjectStatus.ARCHIVED: "project.archived",
                    ProjectStatus.ACTIVE: "project.updated",
                    ProjectStatus.DRAFT: "project.updated",
                }[target_status]
                events.append((event_name, {"status": target_status.value}))

        if "brief" in changes and changes["brief"] is not None:
            normalized = self._normalize_brief(changes["brief"])
            new_hash = brief_hash(normalized)
            try:
                current_hash = brief_hash(row.brief_json)
            except BriefValidationError:
                current_hash = None
            if new_hash != current_hash:
                new_brief_version = row.brief_version + 1
                values["brief_json"] = normalized
                values["brief_version"] = new_brief_version
                brief_history = (new_brief_version, normalized, new_hash)
                events.append(
                    ("project.brief.updated", {"brief_version": new_brief_version, "brief_hash": new_hash})
                )

        if "settings" in changes and changes["settings"] is not None:
            normalized_settings = self._normalize_settings(changes["settings"])
            if normalized_settings != row.settings_json:
                values["settings_json"] = normalized_settings

        if "brand_id" in changes:
            brand_id = changes["brand_id"]
            if brand_id is not None and not isinstance(brand_id, UUID):
                brand_id = UUID(str(brand_id))
            await self._require_brand(organization_id, brand_id)
            if brand_id != row.brand_id:
                values["brand_id"] = brand_id

        if "active_branch_id" in changes:
            active_branch_id = changes["active_branch_id"]
            if active_branch_id is not None and not isinstance(active_branch_id, UUID):
                active_branch_id = UUID(str(active_branch_id))
            await self._require_branch(organization_id, project_id, active_branch_id)
            if active_branch_id != row.active_branch_id:
                values["active_branch_id"] = active_branch_id

        if not values:
            return row

        result = await self.session.execute(
            update(Project)
            .where(
                Project.id == project_id,
                Project.organization_id == organization_id,
                Project.version == expected_version,
                Project.deleted_at.is_(None),
            )
            .values(**values, version=Project.version + 1)
            .returning(Project.version)
        )
        if result.scalar_one_or_none() is None:
            raise ProjectConflict("PROJECT_VERSION_CONFLICT")

        if brief_history is not None:
            version_number, normalized, digest = brief_history
            self.session.add(
                ProjectBriefVersion(
                    id=new_uuid7(),
                    organization_id=organization_id,
                    project_id=project_id,
                    brief_version=version_number,
                    brief_hash=digest,
                    brief_json=normalized,
                    source_input=source_input,
                    created_by=actor_id,
                )
            )
        if not events:
            events.append(("project.updated", {"fields": sorted(values)}))
        elif all(event_name != "project.updated" for event_name, _ in events):
            events.append(("project.updated", {"fields": sorted(values)}))
        for event_name, payload in events:
            self._append_event(
                organization_id=organization_id,
                project_id=project_id,
                name=event_name,
                payload=payload,
            )
        self._append_audit(
            organization_id=organization_id,
            actor_id=actor_id,
            request_id=request_id,
            project_id=project_id,
            action="project.updated",
            metadata={"fields": sorted(values)},
        )
        await self._touch_summary(organization_id, project_id)
        await self.session.flush()
        updated = await self._get_project_row(organization_id, project_id)
        if updated is None:
            raise ProjectNotFound()
        return updated

    async def archive_project(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        project_id: UUID,
        expected_version: int,
    ) -> Project:
        return await self.update_project(
            organization_id=organization_id,
            actor_id=actor_id,
            request_id=request_id,
            project_id=project_id,
            expected_version=expected_version,
            changes={"status": ProjectStatus.ARCHIVED},
        )

    async def restore_project(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        project_id: UUID,
        expected_version: int,
    ) -> Project:
        row = await self._get_project_row(organization_id, project_id)
        if row is None:
            raise ProjectNotFound()
        if row.version != expected_version:
            raise ProjectConflict("PROJECT_VERSION_CONFLICT")
        if row.deleted_at is not None:
            raise ProjectConflict("PROJECT_DELETED")
        try:
            restored = restore(row.status.upper())
        except ValueError as exc:
            raise ProjectConflict(str(exc)) from exc
        result = await self.session.execute(
            update(Project)
            .where(
                Project.id == project_id,
                Project.organization_id == organization_id,
                Project.version == expected_version,
                Project.deleted_at.is_(None),
                Project.status == ProjectStatus.ARCHIVED.value,
            )
            .values(status=restored.lower(), version=Project.version + 1)
            .returning(Project.version)
        )
        if result.scalar_one_or_none() is None:
            raise ProjectConflict("PROJECT_VERSION_CONFLICT")
        self._append_event(
            organization_id=organization_id,
            project_id=project_id,
            name="project.restored",
            payload={"status": restored.lower()},
        )
        self._append_audit(
            organization_id=organization_id,
            actor_id=actor_id,
            request_id=request_id,
            project_id=project_id,
            action="project.restored",
            metadata={"status": restored.lower()},
        )
        await self._touch_summary(organization_id, project_id)
        await self.session.flush()
        restored_row = await self._get_project_row(organization_id, project_id)
        if restored_row is None:
            raise ProjectNotFound()
        return restored_row

    async def list_brief_versions(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> Sequence[ProjectBriefVersion]:
        if await self._get_project_row(organization_id, project_id) is None:
            raise ProjectNotFound()
        result = await self.session.scalars(
            select(ProjectBriefVersion)
            .where(
                ProjectBriefVersion.organization_id == organization_id,
                ProjectBriefVersion.project_id == project_id,
            )
            .order_by(ProjectBriefVersion.brief_version.desc())
        )
        return tuple(result.all())

    async def require_paid_command_allowed(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> None:
        row = await self._get_project_row(organization_id, project_id)
        if row is None:
            raise ProjectNotFound()
        try:
            require_paid_command_allowed(row.status.upper(), deleted=row.deleted_at is not None)
        except ValueError as exc:
            raise ProjectConflict(str(exc)) from exc

    async def _get_project_row(self, organization_id: UUID, project_id: UUID) -> Project | None:
        return await self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
                Project.deleted_at.is_(None),
            )
        )

    async def _require_workspace(self, organization_id: UUID, workspace_id: UUID) -> None:
        row = await self.session.scalar(
            select(Workspace.id).where(
                Workspace.id == workspace_id,
                Workspace.organization_id == organization_id,
            )
        )
        if row is None:
            raise ProjectInvalid("WORKSPACE_NOT_FOUND_OR_FORBIDDEN")

    async def _require_brand(self, organization_id: UUID, brand_id: UUID | None) -> None:
        if brand_id is None:
            return
        row = await self.session.scalar(
            select(Brand.id).where(Brand.id == brand_id, Brand.organization_id == organization_id)
        )
        if row is None:
            raise ProjectInvalid("BRAND_NOT_FOUND_OR_FORBIDDEN")

    async def _require_branch(
        self,
        organization_id: UUID,
        project_id: UUID,
        branch_id: UUID | None,
    ) -> None:
        if branch_id is None:
            return
        row = await self.session.scalar(
            select(ArtifactBranch.id).where(
                ArtifactBranch.id == branch_id,
                ArtifactBranch.organization_id == organization_id,
                ArtifactBranch.project_id == project_id,
            )
        )
        if row is None:
            raise ProjectInvalid("BRANCH_NOT_FOUND_OR_FORBIDDEN")

    async def _touch_summary(self, organization_id: UUID, project_id: UUID) -> None:
        now = datetime.now(UTC)
        summary = await self.session.scalar(
            select(ProjectSummary).where(
                ProjectSummary.organization_id == organization_id,
                ProjectSummary.project_id == project_id,
            )
        )
        if summary is None:
            self.session.add(
                ProjectSummary(
                    id=new_uuid7(),
                    organization_id=organization_id,
                    project_id=project_id,
                    last_activity_at=now,
                    active_run_count=0,
                    artifact_count=0,
                )
            )
        else:
            summary.last_activity_at = now
            summary.version += 1

    def _append_event(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        name: str,
        payload: Mapping[str, Any],
    ) -> None:
        self.session.add(
            OutboxEvent(
                id=new_uuid7(),
                organization_id=organization_id,
                event_name=name,
                aggregate_type="project",
                aggregate_id=project_id,
                schema_version=1,
                payload_json=dict(payload),
            )
        )

    def _append_audit(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_id: str,
        project_id: UUID,
        action: str,
        metadata: Mapping[str, Any],
    ) -> None:
        self.session.add(
            AuditEvent(
                id=new_uuid7(),
                organization_id=organization_id,
                actor_type="user_or_service_token",
                actor_id=actor_id,
                action=action,
                target_type="project",
                target_id=project_id,
                request_id=request_id,
                metadata_json=dict(metadata),
            )
        )

    @staticmethod
    def _normalize_brief(value: Mapping[str, Any] | None) -> dict[str, Any]:
        try:
            return normalize_brief(value)
        except BriefValidationError as exc:
            raise ProjectInvalid("INVALID_PROJECT_BRIEF", str(exc)) from exc

    @staticmethod
    def _normalize_settings(value: Mapping[str, Any] | None) -> dict[str, Any]:
        try:
            return normalize_project_settings(value)
        except ProjectSettingsError as exc:
            raise ProjectInvalid("INVALID_PROJECT_SETTINGS", str(exc)) from exc

    @staticmethod
    def _create_request_hash(
        *,
        workspace_id: UUID,
        name: str,
        brief: Mapping[str, Any],
        brand_id: UUID | None,
        settings: Mapping[str, Any],
    ) -> str:
        payload = {
            "workspace_id": str(workspace_id),
            "name": name,
            "brief": dict(brief),
            "brand_id": str(brand_id) if brand_id else None,
            "settings": dict(settings),
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _to_domain(row: Project) -> DomainProject:
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
