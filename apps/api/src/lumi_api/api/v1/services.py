from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar
from uuid import UUID

from fastapi import Request
from lumi_project_core import ProjectListFilter

from .context import PageRequest, RequestContext
from .contracts import (
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
from .errors import ApiProblem

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


class ApiV1Gateway(Protocol):
    async def list_projects(
        self,
        context: RequestContext,
        page: PageRequest,
        filters: ProjectListFilter,
    ) -> PageResult[ProjectResource]: ...

    async def create_project(
        self, context: RequestContext, payload: ProjectCreate, idempotency_key: str
    ) -> ProjectResource: ...

    async def get_project(self, context: RequestContext, project_id: UUID) -> ProjectResource: ...

    async def update_project(
        self,
        context: RequestContext,
        project_id: UUID,
        payload: ProjectPatch,
        expected_version: int,
    ) -> ProjectResource: ...

    async def archive_project(
        self, context: RequestContext, project_id: UUID, expected_version: int
    ) -> None: ...

    async def restore_project(
        self, context: RequestContext, project_id: UUID, expected_version: int
    ) -> ProjectResource: ...

    async def list_project_brief_versions(
        self, context: RequestContext, project_id: UUID
    ) -> list[ProjectBriefVersionResource]: ...

    async def list_assets(
        self, context: RequestContext, project_id: UUID | None, page: PageRequest
    ) -> PageResult[AssetResource]: ...

    async def create_asset(
        self, context: RequestContext, payload: AssetCreate, idempotency_key: str
    ) -> AssetResource: ...

    async def get_asset(self, context: RequestContext, asset_id: UUID) -> AssetResource: ...

    async def get_artifact(
        self, context: RequestContext, artifact_id: UUID
    ) -> ArtifactResource: ...

    async def list_artifact_versions(
        self, context: RequestContext, artifact_id: UUID, page: PageRequest
    ) -> PageResult[ArtifactVersionResource]: ...

    async def create_artifact_version(
        self,
        context: RequestContext,
        artifact_id: UUID,
        payload: ArtifactVersionCreate,
        idempotency_key: str,
    ) -> ArtifactVersionResource: ...

    async def create_agent_run(
        self, context: RequestContext, payload: AgentRunCreate, idempotency_key: str
    ) -> AgentRunResource: ...

    async def get_agent_run(
        self, context: RequestContext, agent_run_id: UUID
    ) -> AgentRunResource: ...

    async def cancel_agent_run(
        self, context: RequestContext, agent_run_id: UUID, idempotency_key: str
    ) -> AgentRunResource: ...

    async def resume_agent_run(
        self,
        context: RequestContext,
        agent_run_id: UUID,
        payload: AgentRunResumeRequest,
        idempotency_key: str,
    ) -> AgentRunResource: ...

    async def get_task(self, context: RequestContext, task_id: UUID) -> TaskResource: ...

    async def create_generation(
        self, context: RequestContext, payload: GenerationCreate, idempotency_key: str
    ) -> GenerationResource: ...

    async def get_generation(
        self, context: RequestContext, generation_id: UUID
    ) -> GenerationResource: ...

    async def decide_approval(
        self,
        context: RequestContext,
        approval_id: UUID,
        payload: ApprovalDecisionRequest,
        idempotency_key: str,
        expected_version: int,
    ) -> ApprovalResource: ...


def get_api_v1_gateway(request: Request) -> ApiV1Gateway:
    gateway = getattr(request.app.state, "api_v1_gateway", None)
    if gateway is None:
        raise ApiProblem(
            status=501,
            code="APPLICATION_SERVICE_NOT_INSTALLED",
            title="Application service not installed",
            detail=(
                "The HTTP contract is active, but the application-service adapter for this "
                "operation is owned by a later implementation node."
            ),
        )
    return gateway
