from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from lumi_api.auth import AccessPolicyService, Permission, Principal
from lumi_api.domain.ids import new_uuid7
from lumi_api.domain.states import ProjectStatus

from .models import (
    BriefVersion,
    DefaultProjectBranch,
    ProjectBrief,
    ProjectCommandError,
    ProjectEvent,
    ProjectEventType,
    ProjectListQuery,
    ProjectPage,
    ProjectRecord,
    ProjectSettings,
    ProjectSummary,
)
from .store import ProjectRepository


@dataclass(frozen=True, slots=True)
class ProjectCreateCommand:
    organization_id: UUID
    workspace_id: UUID
    name: str
    actor: Principal
    now: datetime
    brief: ProjectBrief = ProjectBrief()
    settings: ProjectSettings = ProjectSettings()
    brand_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ProjectPatchCommand:
    organization_id: UUID
    project_id: UUID
    actor: Principal
    expected_version: int
    now: datetime
    name: str | None = None
    brief: ProjectBrief | None = None
    brand_id: UUID | None = None
    update_brand: bool = False
    settings: ProjectSettings | None = None
    brief_change_reason: str | None = None


class ProjectCoreService:
    def __init__(
        self,
        repository: ProjectRepository,
        *,
        policy: AccessPolicyService | None = None,
    ) -> None:
        self.repository = repository
        self.policy = policy or AccessPolicyService()

    def _authorize(
        self,
        actor: Principal,
        *,
        organization_id: UUID,
        permission: Permission,
    ) -> None:
        decision = self.policy.authorize(
            actor,
            organization_id=organization_id,
            permission=permission,
        )
        if not decision.allowed:
            raise ProjectCommandError(decision.reason_code)

    def get(self, organization_id: UUID, project_id: UUID, *, actor: Principal) -> ProjectRecord:
        self._authorize(actor, organization_id=organization_id, permission=Permission.PROJECT_READ)
        project = self.repository.get(organization_id, project_id)
        if project is None:
            raise ProjectCommandError("PROJECT_NOT_FOUND")
        return project

    def list(self, query: ProjectListQuery, *, actor: Principal) -> ProjectPage:
        self._authorize(
            actor,
            organization_id=query.organization_id,
            permission=Permission.PROJECT_READ,
        )
        return self.repository.list(query)

    def create(self, command: ProjectCreateCommand) -> ProjectRecord:
        self._authorize(
            command.actor,
            organization_id=command.organization_id,
            permission=Permission.PROJECT_WRITE,
        )
        project_id = new_uuid7()
        default_branch_id = new_uuid7()
        project = ProjectRecord(
            id=project_id,
            organization_id=command.organization_id,
            workspace_id=command.workspace_id,
            name=command.name.strip(),
            status=ProjectStatus.DRAFT,
            brief=command.brief,
            brief_version=1,
            brand_id=command.brand_id,
            active_branch_id=None,
            settings=command.settings,
            created_by=command.actor.user_id,
            version=1,
            created_at=command.now,
            updated_at=command.now,
        )
        brief_version = BriefVersion(
            organization_id=project.organization_id,
            project_id=project.id,
            version=1,
            brief=project.brief,
            changed_by=command.actor.user_id,
            change_reason="initial project brief",
            created_at=command.now,
        )
        branch = DefaultProjectBranch(
            id=default_branch_id,
            organization_id=project.organization_id,
            project_id=project.id,
            created_at=command.now,
        )
        summary = ProjectSummary(
            organization_id=project.organization_id,
            project_id=project.id,
            last_activity_at=command.now,
        )
        event = ProjectEvent(
            organization_id=project.organization_id,
            project_id=project.id,
            event_type=ProjectEventType.CREATED,
            actor_id=command.actor.actor_id,
            occurred_at=command.now,
            payload={
                "workspace_id": str(project.workspace_id),
                "brief_version": 1,
                "default_branch_name": branch.name,
            },
        )
        self.repository.insert_creation_bundle(
            project,
            brief_version,
            branch,
            summary,
            (event,),
        )
        return project

    def patch(self, command: ProjectPatchCommand) -> ProjectRecord:
        self._authorize(
            command.actor,
            organization_id=command.organization_id,
            permission=Permission.PROJECT_WRITE,
        )
        current = self.repository.get(command.organization_id, command.project_id)
        if current is None:
            raise ProjectCommandError("PROJECT_NOT_FOUND")
        if current.status == ProjectStatus.ARCHIVED:
            raise ProjectCommandError("PROJECT_ARCHIVED")
        if current.version != command.expected_version:
            raise ProjectCommandError("PROJECT_VERSION_CONFLICT")

        update: dict[str, object] = {
            "version": current.version + 1,
            "updated_at": command.now,
        }
        if command.name is not None:
            update["name"] = command.name.strip()
        if command.settings is not None:
            update["settings"] = command.settings
        if command.update_brand:
            update["brand_id"] = command.brand_id

        brief_version: BriefVersion | None = None
        events: list[ProjectEvent] = []
        if command.brief is not None and command.brief != current.brief:
            next_brief_version = current.brief_version + 1
            update["brief"] = command.brief
            update["brief_version"] = next_brief_version
            brief_version = BriefVersion(
                organization_id=current.organization_id,
                project_id=current.id,
                version=next_brief_version,
                brief=command.brief,
                changed_by=command.actor.user_id,
                change_reason=command.brief_change_reason,
                created_at=command.now,
            )
            events.append(
                ProjectEvent(
                    organization_id=current.organization_id,
                    project_id=current.id,
                    event_type=ProjectEventType.BRIEF_UPDATED,
                    actor_id=command.actor.actor_id,
                    occurred_at=command.now,
                    payload={"brief_version": next_brief_version},
                )
            )
        events.append(
            ProjectEvent(
                organization_id=current.organization_id,
                project_id=current.id,
                event_type=ProjectEventType.UPDATED,
                actor_id=command.actor.actor_id,
                occurred_at=command.now,
                payload={"version": current.version + 1},
            )
        )
        updated = current.model_copy(update=update)
        self.repository.update_project(
            updated,
            expected_version=command.expected_version,
            brief_version=brief_version,
            events=tuple(events),
        )
        return updated

    def transition(
        self,
        organization_id: UUID,
        project_id: UUID,
        target: ProjectStatus,
        *,
        actor: Principal,
        expected_version: int,
        now: datetime,
    ) -> ProjectRecord:
        self._authorize(actor, organization_id=organization_id, permission=Permission.PROJECT_WRITE)
        current = self.repository.get(organization_id, project_id)
        if current is None:
            raise ProjectCommandError("PROJECT_NOT_FOUND")
        if current.version != expected_version:
            raise ProjectCommandError("PROJECT_VERSION_CONFLICT")

        allowed: dict[ProjectStatus, frozenset[ProjectStatus]] = {
            ProjectStatus.DRAFT: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED}),
            ProjectStatus.ACTIVE: frozenset({ProjectStatus.PAUSED, ProjectStatus.ARCHIVED}),
            ProjectStatus.PAUSED: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED}),
            ProjectStatus.ARCHIVED: frozenset({ProjectStatus.ACTIVE}),
        }
        if target not in allowed[current.status]:
            raise ProjectCommandError(
                f"INVALID_PROJECT_TRANSITION:{current.status.value}->{target.value}"
            )

        event_type = ProjectEventType.UPDATED
        if target == ProjectStatus.PAUSED:
            event_type = ProjectEventType.PAUSED
        elif target == ProjectStatus.ARCHIVED:
            event_type = ProjectEventType.ARCHIVED
        elif current.status == ProjectStatus.ARCHIVED and target == ProjectStatus.ACTIVE:
            event_type = ProjectEventType.RESTORED

        updated = current.model_copy(
            update={
                "status": target,
                "version": current.version + 1,
                "updated_at": now,
                "archived_at": now if target == ProjectStatus.ARCHIVED else None,
            }
        )
        event = ProjectEvent(
            organization_id=current.organization_id,
            project_id=current.id,
            event_type=event_type,
            actor_id=actor.actor_id,
            occurred_at=now,
            payload={"from": current.status.value, "to": target.value},
        )
        self.repository.update_project(
            updated,
            expected_version=expected_version,
            brief_version=None,
            events=(event,),
        )
        return updated

    def assert_paid_command_allowed(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        actor: Principal,
    ) -> ProjectRecord:
        project = self.get(organization_id, project_id, actor=actor)
        if project.status == ProjectStatus.ARCHIVED:
            raise ProjectCommandError("PROJECT_ARCHIVED_PAID_COMMAND_BLOCKED")
        if project.status == ProjectStatus.PAUSED:
            raise ProjectCommandError("PROJECT_PAUSED_PAID_COMMAND_BLOCKED")
        return project

    def brief_history(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        actor: Principal,
    ) -> tuple[BriefVersion, ...]:
        self.get(organization_id, project_id, actor=actor)
        return self.repository.list_brief_versions(organization_id, project_id)
