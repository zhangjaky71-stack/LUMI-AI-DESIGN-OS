from datetime import UTC, datetime
from uuid import UUID

from lumi_api.auth import Permission, Principal
from lumi_api.projects import (
    MemoryProjectRepository,
    ProjectCoreService,
    ProjectCreateCommand,
)

ORG = UUID("01910000-0000-7000-8000-000000000001")
USER = UUID("01910000-0000-7000-8000-000000000011")
WORKSPACE = UUID("01910000-0000-7000-8000-000000000021")
NOW = datetime(2026, 8, 16, 15, 55, tzinfo=UTC)


def test_project_create_emits_transactional_audit_with_outbox() -> None:
    repo = MemoryProjectRepository()
    repo.register_workspace(ORG, WORKSPACE)
    actor = Principal(
        actor_type="USER",
        actor_id=str(USER),
        user_id=USER,
        organization_id=ORG,
        roles=("owner",),
        permissions=(Permission.PROJECT_READ.value, Permission.PROJECT_WRITE.value),
    )
    project = ProjectCoreService(repo).create(
        ProjectCreateCommand(
            organization_id=ORG,
            workspace_id=WORKSPACE,
            name="Audited Project",
            actor=actor,
            now=NOW,
        )
    )

    assert len(repo.outbox) == 1
    assert len(repo.audits) == 1
    event = repo.outbox[0]
    audit = repo.audits[0]
    assert event.project_id == audit.project_id == project.id
    assert event.event_type == audit.action
    assert event.actor_id == audit.actor_id == str(USER)
