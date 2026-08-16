from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from lumi_api.api.v1.common import PageMeta
from lumi_api.api.v1.schemas import (
    ProjectBriefHistoryResponse,
    ProjectBriefVersionResponse,
    ProjectCreateRequest,
    ProjectPage as ApiProjectPage,
    ProjectPatchRequest,
    ProjectResponse,
)
from lumi_api.auth import Principal
from lumi_api.domain.states import ProjectStatus

from .models import ProjectListQuery, ProjectRecord
from .service import ProjectCoreService, ProjectCreateCommand, ProjectPatchCommand


class ProjectApiAdapter:
    """Project-method implementation that can be mixed into a composite ApiV1Service."""

    def __init__(self, service: ProjectCoreService, *, principal: Principal) -> None:
        self.service = service
        self.principal = principal

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _response(project: ProjectRecord) -> ProjectResponse:
        return ProjectResponse(
            id=project.id,
            organization_id=project.organization_id,
            workspace_id=project.workspace_id,
            name=project.name,
            status=project.status,
            brief=project.brief,
            brief_version=project.brief_version,
            brand_id=project.brand_id,
            active_branch_id=project.active_branch_id,
            settings=project.settings,
            archived_at=project.archived_at,
            version=project.version,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    async def list_projects(
        self,
        organization_id: UUID,
        *,
        cursor: str | None,
        limit: int,
        status: ProjectStatus | None = None,
        workspace_id: UUID | None = None,
        created_by: UUID | None = None,
        updated_from: datetime | None = None,
        updated_to: datetime | None = None,
        name_query: str | None = None,
    ) -> ApiProjectPage:
        page = self.service.list(
            ProjectListQuery(
                organization_id=organization_id,
                status=status,
                workspace_id=workspace_id,
                created_by=created_by,
                updated_from=updated_from,
                updated_to=updated_to,
                name_query=name_query,
                cursor=cursor,
                limit=limit,
            ),
            actor=self.principal,
        )
        return ApiProjectPage(
            items=[self._response(item) for item in page.items],
            meta=PageMeta(next_cursor=page.next_cursor, has_more=page.next_cursor is not None),
        )

    async def create_project(
        self,
        organization_id: UUID,
        request: ProjectCreateRequest,
        *,
        idempotency_key: str,
    ) -> ProjectResponse:
        if not idempotency_key.strip():
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        project = self.service.create(
            ProjectCreateCommand(
                organization_id=organization_id,
                workspace_id=request.workspace_id,
                name=request.name,
                actor=self.principal,
                now=self._now(),
                brief=request.brief,
                settings=request.settings,
                brand_id=request.brand_id,
            )
        )
        return self._response(project)

    async def get_project(
        self, organization_id: UUID, project_id: UUID
    ) -> ProjectResponse:
        return self._response(
            self.service.get(organization_id, project_id, actor=self.principal)
        )

    async def get_project_brief_history(
        self, organization_id: UUID, project_id: UUID
    ) -> ProjectBriefHistoryResponse:
        history = self.service.brief_history(
            organization_id, project_id, actor=self.principal
        )
        return ProjectBriefHistoryResponse(
            project_id=project_id,
            items=[
                ProjectBriefVersionResponse(
                    id=item.id,
                    organization_id=item.organization_id,
                    project_id=item.project_id,
                    version=item.version,
                    brief=item.brief,
                    changed_by=item.changed_by,
                    change_reason=item.change_reason,
                    created_at=item.created_at,
                )
                for item in history
            ],
        )

    async def patch_project(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: ProjectPatchRequest,
        *,
        expected_version: int,
    ) -> ProjectResponse:
        fields_set = request.model_fields_set
        project = self.service.patch(
            ProjectPatchCommand(
                organization_id=organization_id,
                project_id=project_id,
                actor=self.principal,
                expected_version=expected_version,
                now=self._now(),
                name=request.name,
                brief=request.brief,
                brand_id=request.brand_id,
                update_brand="brand_id" in fields_set,
                settings=request.settings,
                brief_change_reason=request.brief_change_reason,
            )
        )
        return self._response(project)

    async def transition_project(
        self,
        organization_id: UUID,
        project_id: UUID,
        target: ProjectStatus,
        *,
        expected_version: int,
    ) -> ProjectResponse:
        project = self.service.transition(
            organization_id,
            project_id,
            target,
            actor=self.principal,
            expected_version=expected_version,
            now=self._now(),
        )
        return self._response(project)
