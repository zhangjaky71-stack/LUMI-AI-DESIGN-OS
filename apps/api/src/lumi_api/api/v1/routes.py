from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from lumi_api.domain.states import ProjectStatus

from .common import ProblemDetail, parse_if_match, version_etag
from .dependencies import ApiServiceDependency
from .errors import ApiProblem
from .headers import IdempotencyKey, IfMatch, OrganizationId
from .schemas import (
    AgentRunCreateRequest,
    AgentRunResponse,
    ArtifactVersionResponse,
    CancelResponse,
    GenerationCreateRequest,
    GenerationResponse,
    ProjectBriefHistoryResponse,
    ProjectCreateRequest,
    ProjectPage,
    ProjectPatchRequest,
    ProjectResponse,
    ProjectTransitionRequest,
    TaskCreateRequest,
    TaskPage,
    TaskResponse,
)

router = APIRouter(prefix="/api/v1")

_ERROR_RESPONSES = {
    400: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _expected_version(if_match: str) -> int:
    try:
        return parse_if_match(if_match)
    except ValueError as exc:
        raise ApiProblem(
            status=400,
            code="invalid_if_match",
            title="Invalid If-Match header",
            detail=str(exc),
        ) from exc


def _set_version_headers(response: Response, version: int) -> None:
    response.headers["ETag"] = version_etag(version)
    response.headers["Cache-Control"] = "private, no-cache"


@router.get(
    "/projects",
    response_model=ProjectPage,
    responses=_ERROR_RESPONSES,
    tags=["projects"],
)
async def list_projects(
    organization_id: OrganizationId,
    service: ApiServiceDependency,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    workspace_id: UUID | None = None,
    created_by: UUID | None = None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
    name_query: Annotated[str | None, Query(alias="q", min_length=1, max_length=240)] = None,
) -> ProjectPage:
    return await service.list_projects(
        organization_id,
        cursor=cursor,
        limit=limit,
        status=project_status,
        workspace_id=workspace_id,
        created_by=created_by,
        updated_from=updated_from,
        updated_to=updated_to,
        name_query=name_query,
    )


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["projects"],
)
async def create_project(
    request: ProjectCreateRequest,
    response: Response,
    organization_id: OrganizationId,
    idempotency_key: IdempotencyKey,
    service: ApiServiceDependency,
) -> ProjectResponse:
    project = await service.create_project(
        organization_id,
        request,
        idempotency_key=idempotency_key,
    )
    _set_version_headers(response, project.version)
    response.headers["Location"] = f"/api/v1/projects/{project.id}"
    return project


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    responses=_ERROR_RESPONSES,
    tags=["projects"],
)
async def get_project(
    project_id: UUID,
    response: Response,
    organization_id: OrganizationId,
    service: ApiServiceDependency,
) -> ProjectResponse:
    project = await service.get_project(organization_id, project_id)
    _set_version_headers(response, project.version)
    return project


@router.get(
    "/projects/{project_id}/brief/versions",
    response_model=ProjectBriefHistoryResponse,
    responses=_ERROR_RESPONSES,
    tags=["projects"],
)
async def get_project_brief_history(
    project_id: UUID,
    organization_id: OrganizationId,
    service: ApiServiceDependency,
) -> ProjectBriefHistoryResponse:
    return await service.get_project_brief_history(organization_id, project_id)


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    responses=_ERROR_RESPONSES,
    tags=["projects"],
)
async def patch_project(
    project_id: UUID,
    request: ProjectPatchRequest,
    response: Response,
    organization_id: OrganizationId,
    if_match: IfMatch,
    service: ApiServiceDependency,
) -> ProjectResponse:
    project = await service.patch_project(
        organization_id,
        project_id,
        request,
        expected_version=_expected_version(if_match),
    )
    _set_version_headers(response, project.version)
    return project


@router.post(
    "/projects/{project_id}/transitions",
    response_model=ProjectResponse,
    responses=_ERROR_RESPONSES,
    tags=["projects"],
)
async def transition_project(
    project_id: UUID,
    request: ProjectTransitionRequest,
    response: Response,
    organization_id: OrganizationId,
    if_match: IfMatch,
    service: ApiServiceDependency,
) -> ProjectResponse:
    project = await service.transition_project(
        organization_id,
        project_id,
        request.target,
        expected_version=_expected_version(if_match),
    )
    _set_version_headers(response, project.version)
    return project


@router.delete(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    responses=_ERROR_RESPONSES,
    tags=["projects"],
)
async def archive_project(
    project_id: UUID,
    response: Response,
    organization_id: OrganizationId,
    if_match: IfMatch,
    service: ApiServiceDependency,
) -> ProjectResponse:
    project = await service.transition_project(
        organization_id,
        project_id,
        ProjectStatus.ARCHIVED,
        expected_version=_expected_version(if_match),
    )
    _set_version_headers(response, project.version)
    return project


@router.post(
    "/projects/{project_id}/restore",
    response_model=ProjectResponse,
    responses=_ERROR_RESPONSES,
    tags=["projects"],
)
async def restore_project(
    project_id: UUID,
    response: Response,
    organization_id: OrganizationId,
    if_match: IfMatch,
    service: ApiServiceDependency,
) -> ProjectResponse:
    project = await service.transition_project(
        organization_id,
        project_id,
        ProjectStatus.ACTIVE,
        expected_version=_expected_version(if_match),
    )
    _set_version_headers(response, project.version)
    return project


@router.get(
    "/projects/{project_id}/tasks",
    response_model=TaskPage,
    responses=_ERROR_RESPONSES,
    tags=["tasks"],
)
async def list_tasks(
    project_id: UUID,
    organization_id: OrganizationId,
    service: ApiServiceDependency,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TaskPage:
    return await service.list_tasks(
        organization_id,
        project_id,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["tasks"],
)
async def create_task(
    project_id: UUID,
    request: TaskCreateRequest,
    response: Response,
    organization_id: OrganizationId,
    idempotency_key: IdempotencyKey,
    service: ApiServiceDependency,
) -> TaskResponse:
    task = await service.create_task(
        organization_id,
        project_id,
        request,
        idempotency_key=idempotency_key,
    )
    _set_version_headers(response, task.version)
    response.headers["Location"] = f"/api/v1/tasks/{task.id}"
    return task


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    responses=_ERROR_RESPONSES,
    tags=["tasks"],
)
async def get_task(
    task_id: UUID,
    response: Response,
    organization_id: OrganizationId,
    service: ApiServiceDependency,
) -> TaskResponse:
    task = await service.get_task(organization_id, task_id)
    _set_version_headers(response, task.version)
    return task


@router.post(
    "/projects/{project_id}/agent-runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
    tags=["agent-runs"],
)
async def create_agent_run(
    project_id: UUID,
    request: AgentRunCreateRequest,
    response: Response,
    organization_id: OrganizationId,
    idempotency_key: IdempotencyKey,
    service: ApiServiceDependency,
) -> AgentRunResponse:
    run = await service.create_agent_run(
        organization_id,
        project_id,
        request,
        idempotency_key=idempotency_key,
    )
    _set_version_headers(response, run.version)
    response.headers["Location"] = f"/api/v1/agent-runs/{run.id}"
    return run


@router.get(
    "/agent-runs/{agent_run_id}",
    response_model=AgentRunResponse,
    responses=_ERROR_RESPONSES,
    tags=["agent-runs"],
)
async def get_agent_run(
    agent_run_id: UUID,
    response: Response,
    organization_id: OrganizationId,
    service: ApiServiceDependency,
) -> AgentRunResponse:
    run = await service.get_agent_run(organization_id, agent_run_id)
    _set_version_headers(response, run.version)
    return run


@router.post(
    "/agent-runs/{agent_run_id}/cancel",
    response_model=CancelResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
    tags=["agent-runs"],
)
async def cancel_agent_run(
    agent_run_id: UUID,
    organization_id: OrganizationId,
    idempotency_key: IdempotencyKey,
    service: ApiServiceDependency,
) -> CancelResponse:
    return await service.cancel_agent_run(
        organization_id,
        agent_run_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/projects/{project_id}/generations",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
    tags=["generations"],
)
async def create_generation(
    project_id: UUID,
    request: GenerationCreateRequest,
    response: Response,
    organization_id: OrganizationId,
    idempotency_key: IdempotencyKey,
    service: ApiServiceDependency,
) -> GenerationResponse:
    generation = await service.create_generation(
        organization_id,
        project_id,
        request,
        idempotency_key=idempotency_key,
    )
    _set_version_headers(response, generation.version)
    response.headers["Location"] = f"/api/v1/generations/{generation.id}"
    return generation


@router.get(
    "/generations/{generation_id}",
    response_model=GenerationResponse,
    responses=_ERROR_RESPONSES,
    tags=["generations"],
)
async def get_generation(
    generation_id: UUID,
    response: Response,
    organization_id: OrganizationId,
    service: ApiServiceDependency,
) -> GenerationResponse:
    generation = await service.get_generation(organization_id, generation_id)
    _set_version_headers(response, generation.version)
    return generation


@router.get(
    "/artifact-versions/{artifact_version_id}",
    response_model=ArtifactVersionResponse,
    responses=_ERROR_RESPONSES,
    tags=["artifacts"],
)
async def get_artifact_version(
    artifact_version_id: UUID,
    organization_id: OrganizationId,
    service: ApiServiceDependency,
) -> ArtifactVersionResponse:
    return await service.get_artifact_version(organization_id, artifact_version_id)
