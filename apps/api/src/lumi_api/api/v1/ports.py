from __future__ import annotations

from typing import Protocol
from uuid import UUID

from lumi_api.domain.states import ProjectStatus

from .schemas import (
    AgentRunCreateRequest,
    AgentRunResponse,
    ArtifactVersionResponse,
    CancelResponse,
    GenerationCreateRequest,
    GenerationResponse,
    ProjectCreateRequest,
    ProjectPage,
    ProjectPatchRequest,
    ProjectResponse,
    TaskCreateRequest,
    TaskPage,
    TaskResponse,
)


class ApiV1Service(Protocol):
    async def list_projects(
        self,
        organization_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> ProjectPage: ...

    async def create_project(
        self,
        organization_id: UUID,
        request: ProjectCreateRequest,
        *,
        idempotency_key: str,
    ) -> ProjectResponse: ...

    async def get_project(
        self, organization_id: UUID, project_id: UUID
    ) -> ProjectResponse: ...

    async def patch_project(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: ProjectPatchRequest,
        *,
        expected_version: int,
    ) -> ProjectResponse: ...

    async def transition_project(
        self,
        organization_id: UUID,
        project_id: UUID,
        target: ProjectStatus,
        *,
        expected_version: int,
    ) -> ProjectResponse: ...

    async def list_tasks(
        self,
        organization_id: UUID,
        project_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> TaskPage: ...

    async def create_task(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: TaskCreateRequest,
        *,
        idempotency_key: str,
    ) -> TaskResponse: ...

    async def get_task(self, organization_id: UUID, task_id: UUID) -> TaskResponse: ...

    async def create_agent_run(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: AgentRunCreateRequest,
        *,
        idempotency_key: str,
    ) -> AgentRunResponse: ...

    async def get_agent_run(
        self, organization_id: UUID, agent_run_id: UUID
    ) -> AgentRunResponse: ...

    async def cancel_agent_run(
        self,
        organization_id: UUID,
        agent_run_id: UUID,
        *,
        idempotency_key: str,
    ) -> CancelResponse: ...

    async def create_generation(
        self,
        organization_id: UUID,
        project_id: UUID,
        request: GenerationCreateRequest,
        *,
        idempotency_key: str,
    ) -> GenerationResponse: ...

    async def get_generation(
        self, organization_id: UUID, generation_id: UUID
    ) -> GenerationResponse: ...

    async def get_artifact_version(
        self, organization_id: UUID, artifact_version_id: UUID
    ) -> ArtifactVersionResponse: ...
