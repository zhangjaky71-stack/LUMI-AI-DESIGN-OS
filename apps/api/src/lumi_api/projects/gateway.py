from __future__ import annotations

from uuid import UUID

from lumi_domain import ProjectStatus
from lumi_project_core import ProjectListFilter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.api.v1.context import PageRequest, RequestContext
from lumi_api.api.v1.contracts import (
    AgentRunCreate,
    AgentRunResource,
    AgentRunResumeRequest,
    ApprovalDecisionRequest,
    ApprovalResource,
    ArtifactResource,
    ArtifactVersionCreate,
    ArtifactVersionResource,
    AssetCreate,
    AssetResource,
    GenerationCreate,
    GenerationResource,
    ProjectBriefVersionResource,
    ProjectCreate,
    ProjectPatch,
    ProjectResource,
    TaskResource,
)
from lumi_api.api.v1.errors import ApiProblem
from lumi_api.api.v1.services import PageResult
from lumi_api.persistence.models import Project, ProjectBriefVersion

from .errors import ProjectApplicationError, ProjectConflict, ProjectInvalid, ProjectNotFound
from .service import ProjectService


class ProjectCoreGateway:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_projects(
        self,
        context: RequestContext,
        page: PageRequest,
        filters: ProjectListFilter,
    ) -> PageResult[ProjectResource]:
        self._require(context, "project.read")
        async with self.session_factory() as session, session.begin():
            try:
                rows, next_cursor, has_more = await ProjectService(session).list_projects(
                    organization_id=context.organization_id,
                    filters=filters,
                    cursor=page.cursor,
                    limit=page.limit,
                )
            except ProjectApplicationError as exc:
                raise self._problem(exc) from exc
            return PageResult(
                items=[self._project_resource(row) for row in rows],
                next_cursor=next_cursor,
                has_more=has_more,
            )

    async def create_project(
        self,
        context: RequestContext,
        payload: ProjectCreate,
        idempotency_key: str,
    ) -> ProjectResource:
        actor_id = self._require(context, "project.write")
        async with self.session_factory() as session, session.begin():
            try:
                row = await ProjectService(session).create_project(
                    organization_id=context.organization_id,
                    actor_id=actor_id,
                    request_id=context.request_id,
                    idempotency_key=idempotency_key,
                    workspace_id=payload.workspace_id,
                    name=payload.name,
                    brief=payload.brief,
                    brand_id=payload.brand_id,
                    settings=payload.settings,
                )
            except ProjectApplicationError as exc:
                raise self._problem(exc) from exc
            await session.refresh(row)
            return self._project_resource(row)

    async def get_project(self, context: RequestContext, project_id: UUID) -> ProjectResource:
        self._require(context, "project.read")
        async with self.session_factory() as session, session.begin():
            try:
                row = await ProjectService(session).get_project(
                    organization_id=context.organization_id,
                    project_id=project_id,
                )
            except ProjectApplicationError as exc:
                raise self._problem(exc) from exc
            return self._project_resource(row)

    async def update_project(
        self,
        context: RequestContext,
        project_id: UUID,
        payload: ProjectPatch,
        expected_version: int,
    ) -> ProjectResource:
        actor_id = self._require(context, "project.write")
        async with self.session_factory() as session, session.begin():
            try:
                row = await ProjectService(session).update_project(
                    organization_id=context.organization_id,
                    actor_id=actor_id,
                    request_id=context.request_id,
                    project_id=project_id,
                    expected_version=expected_version,
                    changes=payload.model_dump(exclude_unset=True),
                )
            except ProjectApplicationError as exc:
                raise self._problem(exc) from exc
            except ValueError as exc:
                raise ApiProblem(
                    status=422,
                    code="INVALID_PROJECT_UPDATE",
                    title="Invalid project update",
                    detail=str(exc),
                ) from exc
            return self._project_resource(row)

    async def archive_project(
        self,
        context: RequestContext,
        project_id: UUID,
        expected_version: int,
    ) -> None:
        actor_id = self._require(context, "project.write")
        async with self.session_factory() as session, session.begin():
            try:
                await ProjectService(session).archive_project(
                    organization_id=context.organization_id,
                    actor_id=actor_id,
                    request_id=context.request_id,
                    project_id=project_id,
                    expected_version=expected_version,
                )
            except ProjectApplicationError as exc:
                raise self._problem(exc) from exc

    async def restore_project(
        self,
        context: RequestContext,
        project_id: UUID,
        expected_version: int,
    ) -> ProjectResource:
        actor_id = self._require(context, "project.write")
        async with self.session_factory() as session, session.begin():
            try:
                row = await ProjectService(session).restore_project(
                    organization_id=context.organization_id,
                    actor_id=actor_id,
                    request_id=context.request_id,
                    project_id=project_id,
                    expected_version=expected_version,
                )
            except ProjectApplicationError as exc:
                raise self._problem(exc) from exc
            return self._project_resource(row)

    async def list_project_brief_versions(
        self,
        context: RequestContext,
        project_id: UUID,
    ) -> list[ProjectBriefVersionResource]:
        self._require(context, "project.read")
        async with self.session_factory() as session, session.begin():
            try:
                rows = await ProjectService(session).list_brief_versions(
                    organization_id=context.organization_id,
                    project_id=project_id,
                )
            except ProjectApplicationError as exc:
                raise self._problem(exc) from exc
            return [self._brief_resource(row) for row in rows]

    async def list_assets(
        self, context: RequestContext, project_id: UUID | None, page: PageRequest
    ) -> PageResult[AssetResource]:
        raise self._not_implemented("NODE-18 Asset Storage")

    async def create_asset(
        self, context: RequestContext, payload: AssetCreate, idempotency_key: str
    ) -> AssetResource:
        raise self._not_implemented("NODE-18 Asset Storage")

    async def get_asset(self, context: RequestContext, asset_id: UUID) -> AssetResource:
        raise self._not_implemented("NODE-18 Asset Storage")

    async def get_artifact(self, context: RequestContext, artifact_id: UUID) -> ArtifactResource:
        raise self._not_implemented("Artifact runtime")

    async def list_artifact_versions(
        self, context: RequestContext, artifact_id: UUID, page: PageRequest
    ) -> PageResult[ArtifactVersionResource]:
        raise self._not_implemented("Artifact runtime")

    async def create_artifact_version(
        self,
        context: RequestContext,
        artifact_id: UUID,
        payload: ArtifactVersionCreate,
        idempotency_key: str,
    ) -> ArtifactVersionResource:
        raise self._not_implemented("Artifact runtime")

    async def create_agent_run(
        self, context: RequestContext, payload: AgentRunCreate, idempotency_key: str
    ) -> AgentRunResource:
        raise self._not_implemented("Agent runtime")

    async def get_agent_run(self, context: RequestContext, agent_run_id: UUID) -> AgentRunResource:
        raise self._not_implemented("Agent runtime")

    async def cancel_agent_run(
        self, context: RequestContext, agent_run_id: UUID, idempotency_key: str
    ) -> AgentRunResource:
        raise self._not_implemented("Agent runtime")

    async def resume_agent_run(
        self,
        context: RequestContext,
        agent_run_id: UUID,
        payload: AgentRunResumeRequest,
        idempotency_key: str,
    ) -> AgentRunResource:
        raise self._not_implemented("Agent runtime")

    async def get_task(self, context: RequestContext, task_id: UUID) -> TaskResource:
        raise self._not_implemented("Task runtime")

    async def create_generation(
        self, context: RequestContext, payload: GenerationCreate, idempotency_key: str
    ) -> GenerationResource:
        raise self._not_implemented("Generation runtime")

    async def get_generation(
        self, context: RequestContext, generation_id: UUID
    ) -> GenerationResource:
        raise self._not_implemented("Generation runtime")

    async def decide_approval(
        self,
        context: RequestContext,
        approval_id: UUID,
        payload: ApprovalDecisionRequest,
        idempotency_key: str,
        expected_version: int,
    ) -> ApprovalResource:
        raise self._not_implemented("Approval runtime")

    @staticmethod
    def _project_resource(row: Project) -> ProjectResource:
        return ProjectResource(
            id=row.id,
            organization_id=row.organization_id,
            workspace_id=row.workspace_id,
            name=row.name,
            status=ProjectStatus(row.status),
            brief=dict(row.brief_json),
            brief_version=row.brief_version,
            brand_id=row.brand_id,
            active_branch_id=row.active_branch_id,
            settings=dict(row.settings_json),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _brief_resource(row: ProjectBriefVersion) -> ProjectBriefVersionResource:
        return ProjectBriefVersionResource(
            id=row.id,
            project_id=row.project_id,
            brief_version=row.brief_version,
            brief_hash=row.brief_hash,
            brief=dict(row.brief_json),
            created_by=row.created_by,
            created_at=row.created_at,
        )

    @staticmethod
    def _require(context: RequestContext, permission: str) -> UUID:
        if context.actor_id is None or permission not in context.permissions:
            raise ApiProblem(status=403, code="PERMISSION_DENIED", title="Permission denied")
        return context.actor_id

    @staticmethod
    def _problem(error: ProjectApplicationError) -> ApiProblem:
        if isinstance(error, ProjectNotFound):
            return ApiProblem(
                status=404,
                code="PROJECT_NOT_FOUND_OR_FORBIDDEN",
                title="Resource not found",
            )
        if isinstance(error, ProjectConflict):
            return ApiProblem(
                status=409,
                code=error.code,
                title="Project conflict",
                detail=str(error),
            )
        if isinstance(error, ProjectInvalid):
            return ApiProblem(
                status=422,
                code=error.code,
                title="Invalid project request",
                detail=str(error),
            )
        return ApiProblem(
            status=500,
            code="PROJECT_OPERATION_FAILED",
            title="Project operation failed",
        )

    @staticmethod
    def _not_implemented(owner: str) -> ApiProblem:
        return ApiProblem(
            status=501,
            code="APPLICATION_SERVICE_NOT_INSTALLED",
            title="Application service not installed",
            detail=f"This operation is owned by {owner}, not NODE-17 Project Core.",
        )
