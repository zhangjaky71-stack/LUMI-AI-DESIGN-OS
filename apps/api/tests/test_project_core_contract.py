from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lumi_api.auth import Permission, Principal
from lumi_api.domain.ids import new_uuid7
from lumi_api.domain.states import ProjectStatus
from lumi_api.projects import (
    MemoryProjectRepository,
    ProjectBrief,
    ProjectCommandError,
    ProjectCoreService,
    ProjectCreateCommand,
    ProjectListQuery,
    ProjectPatchCommand,
    ProjectSettings,
)

NOW = datetime(2026, 8, 16, 15, 45, tzinfo=UTC)
ORG_A = UUID("01910000-0000-7000-8000-000000000001")
ORG_B = UUID("01910000-0000-7000-8000-000000000002")
USER_A = UUID("01910000-0000-7000-8000-000000000011")
WORKSPACE_A = UUID("01910000-0000-7000-8000-000000000021")


def principal(org: UUID = ORG_A, *, write: bool = True) -> Principal:
    permissions = [Permission.PROJECT_READ.value]
    if write:
        permissions.append(Permission.PROJECT_WRITE.value)
    return Principal(
        actor_type="USER",
        actor_id=str(USER_A),
        user_id=USER_A,
        organization_id=org,
        roles=("owner",),
        permissions=tuple(permissions),
    )


def create_project(service: ProjectCoreService, *, name: str = "Coffee Rebrand"):
    return service.create(
        ProjectCreateCommand(
            organization_id=ORG_A,
            workspace_id=WORKSPACE_A,
            name=name,
            actor=principal(),
            now=NOW,
            brief=ProjectBrief(
                objective="Rebrand a premium coffee concept",
                audience=("urban professionals",),
                deliverables=("mobile campaign", "store poster"),
                channels=("app", "print"),
                locale="zh-CN",
            ),
            settings=ProjectSettings(default_locale="zh-CN", timezone="Asia/Shanghai"),
        )
    )


def test_create_is_single_bundle_with_brief_branch_summary_and_event() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    project = create_project(service)

    assert project.brief_version == 1
    assert project.active_branch_id is None
    assert len(repo.briefs[project.id]) == 1
    assert next(iter(repo.branches.values())).project_id == project.id
    assert repo.summaries[project.id].artifact_count == 0
    assert [event.event_type.value for event in repo.outbox] == ["project.created"]


def test_structured_brief_version_increments_only_on_material_change() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    project = create_project(service)
    same = service.patch(
        ProjectPatchCommand(
            organization_id=ORG_A,
            project_id=project.id,
            actor=principal(),
            expected_version=1,
            now=NOW + timedelta(minutes=1),
            brief=project.brief,
            name="Coffee Rebrand V2",
        )
    )
    assert same.brief_version == 1
    assert len(repo.briefs[project.id]) == 1

    updated_brief = project.brief.model_copy(update={"objective": "Launch the new coffee identity"})
    changed = service.patch(
        ProjectPatchCommand(
            organization_id=ORG_A,
            project_id=project.id,
            actor=principal(),
            expected_version=2,
            now=NOW + timedelta(minutes=2),
            brief=updated_brief,
            brief_change_reason="launch scope approved",
        )
    )
    assert changed.brief_version == 2
    assert [item.version for item in repo.briefs[project.id]] == [1, 2]
    assert repo.briefs[project.id][-1].change_reason == "launch scope approved"


def test_optimistic_concurrency_rejects_stale_patch() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    project = create_project(service)
    service.patch(
        ProjectPatchCommand(
            organization_id=ORG_A,
            project_id=project.id,
            actor=principal(),
            expected_version=1,
            now=NOW + timedelta(minutes=1),
            name="Updated",
        )
    )
    with pytest.raises(ProjectCommandError, match="PROJECT_VERSION_CONFLICT"):
        service.patch(
            ProjectPatchCommand(
                organization_id=ORG_A,
                project_id=project.id,
                actor=principal(),
                expected_version=1,
                now=NOW + timedelta(minutes=2),
                name="Stale",
            )
        )


def test_archive_blocks_paid_command_and_restore_creates_new_version() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    project = create_project(service)
    active = service.transition(
        ORG_A,
        project.id,
        ProjectStatus.ACTIVE,
        actor=principal(),
        expected_version=1,
        now=NOW + timedelta(minutes=1),
    )
    archived = service.transition(
        ORG_A,
        project.id,
        ProjectStatus.ARCHIVED,
        actor=principal(),
        expected_version=active.version,
        now=NOW + timedelta(minutes=2),
    )
    assert archived.archived_at is not None
    with pytest.raises(ProjectCommandError, match="PROJECT_ARCHIVED_PAID_COMMAND_BLOCKED"):
        service.assert_paid_command_allowed(ORG_A, project.id, actor=principal())

    restored = service.transition(
        ORG_A,
        project.id,
        ProjectStatus.ACTIVE,
        actor=principal(),
        expected_version=archived.version,
        now=NOW + timedelta(minutes=3),
    )
    assert restored.version == archived.version + 1
    assert restored.archived_at is None
    assert repo.outbox[-1].event_type.value == "project.restored"


def test_pause_preserves_project_and_blocks_new_paid_command() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    project = create_project(service)
    active = service.transition(
        ORG_A,
        project.id,
        ProjectStatus.ACTIVE,
        actor=principal(),
        expected_version=1,
        now=NOW + timedelta(minutes=1),
    )
    paused = service.transition(
        ORG_A,
        project.id,
        ProjectStatus.PAUSED,
        actor=principal(),
        expected_version=active.version,
        now=NOW + timedelta(minutes=2),
    )
    assert repo.get(ORG_A, project.id) == paused
    with pytest.raises(ProjectCommandError, match="PROJECT_PAUSED_PAID_COMMAND_BLOCKED"):
        service.assert_paid_command_allowed(ORG_A, project.id, actor=principal())


def test_cross_tenant_lookup_is_indistinguishable_from_missing() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    project = create_project(service)
    with pytest.raises(ProjectCommandError, match="TENANT_RESOURCE_NOT_FOUND"):
        service.get(ORG_B, project.id, actor=principal(ORG_A))
    assert repo.get(ORG_B, project.id) is None


def test_read_only_principal_cannot_mutate_project() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    with pytest.raises(ProjectCommandError, match="PERMISSION_DENIED"):
        service.create(
            ProjectCreateCommand(
                organization_id=ORG_A,
                workspace_id=WORKSPACE_A,
                name="Forbidden",
                actor=principal(write=False),
                now=NOW,
            )
        )


def test_cursor_pagination_is_stable_and_tenant_scoped() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    for index in range(5):
        project = create_project(service, name=f"Project {index}")
        if index:
            service.patch(
                ProjectPatchCommand(
                    organization_id=ORG_A,
                    project_id=project.id,
                    actor=principal(),
                    expected_version=1,
                    now=NOW + timedelta(minutes=index),
                    name=f"Project {index} updated",
                )
            )
    first = service.list(ProjectListQuery(organization_id=ORG_A, limit=2), actor=principal())
    assert len(first.items) == 2
    assert first.next_cursor is not None
    second = service.list(
        ProjectListQuery(organization_id=ORG_A, limit=2, cursor=first.next_cursor),
        actor=principal(),
    )
    assert len(second.items) == 2
    assert {p.id for p in first.items}.isdisjoint({p.id for p in second.items})


def test_list_filters_by_workspace_status_creator_and_name() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    project = create_project(service, name="Coffee Alpha")
    service.transition(
        ORG_A,
        project.id,
        ProjectStatus.ACTIVE,
        actor=principal(),
        expected_version=1,
        now=NOW + timedelta(minutes=1),
    )
    result = service.list(
        ProjectListQuery(
            organization_id=ORG_A,
            workspace_id=WORKSPACE_A,
            status=ProjectStatus.ACTIVE,
            created_by=USER_A,
            name_query="coffee",
        ),
        actor=principal(),
    )
    assert [item.id for item in result.items] == [project.id]


def test_project_settings_reject_extra_secret_fields() -> None:
    with pytest.raises(Exception):
        ProjectSettings.model_validate({"default_locale": "en-US", "provider_api_key": "secret"})


def test_brief_rejects_duplicate_semantic_list_values() -> None:
    with pytest.raises(ValueError, match="unique"):
        ProjectBrief(audience=("designer", "designer"))


def test_invalid_cursor_fails_closed() -> None:
    repo = MemoryProjectRepository()
    service = ProjectCoreService(repo)
    create_project(service)
    with pytest.raises(ValueError, match="INVALID_PROJECT_CURSOR"):
        service.list(
            ProjectListQuery(organization_id=ORG_A, cursor="not-a-valid-cursor"),
            actor=principal(),
        )
