from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from lumi_project_core import ProjectListFilter

from .context import (
    PageRequest,
    RequestContext,
    get_page_request,
    get_project_list_filter,
    get_request_context,
    require_idempotency_key,
    require_if_match_version,
    version_etag,
)
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
    CollectionEnvelope,
    DataEnvelope,
    GenerationCreate,
    GenerationResource,
    HealthResource,
    PageMeta,
    ProblemDetails,
    ProjectBriefVersionResource,
    ProjectCreate,
    ProjectPatch,
    ProjectResource,
    ResponseMeta,
    TaskResource,
)
from .errors import problem_responses
from .services import ApiV1Gateway, get_api_v1_gateway

router = APIRouter(prefix="/api/v1")

ContextDep = Annotated[RequestContext, Depends(get_request_context)]
PageDep = Annotated[PageRequest, Depends(get_page_request)]
ProjectFilterDep = Annotated[ProjectListFilter, Depends(get_project_list_filter)]
GatewayDep = Annotated[ApiV1Gateway, Depends(get_api_v1_gateway)]
IdempotencyDep = Annotated[str, Depends(require_idempotency_key)]
IfMatchDep = Annotated[int, Depends(require_if_match_version)]


def _meta(context: RequestContext) -> ResponseMeta:
    return ResponseMeta(request_id=context.request_id)


def _page_meta(context: RequestContext, result: object) -> PageMeta:
    next_cursor = getattr(result, "next_cursor", None)
    has_more = bool(getattr(result, "has_more", False))
    return PageMeta(
        request_id=context.request_id,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def _set_version_etag(response: Response, version: int) -> None:
    response.headers["ETag"] = version_etag(version)


@router.get(
    "/health",
    operation_id="getApiV1Health",
    response_model=DataEnvelope[HealthResource],
    tags=["system"],
)
async def health() -> DataEnvelope[HealthResource]:
    return DataEnvelope(
        data=HealthResource(),
        meta=ResponseMeta(request_id="health"),
    )


@router.get(
    "/projects",
    operation_id="listProjects",
    response_model=CollectionEnvelope[ProjectResource],
    responses=problem_responses(),
    tags=["projects"],
)
async def list_projects(
    context: ContextDep,
    page: PageDep,
    filters: ProjectFilterDep,
    gateway: GatewayDep,
) -> CollectionEnvelope[ProjectResource]:
    result = await gateway.list_projects(context, page, filters)
    return CollectionEnvelope(data=result.items, meta=_page_meta(context, result))


@router.post(
    "/projects",
    operation_id="createProject",
    response_model=DataEnvelope[ProjectResource],
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(),
    tags=["projects"],
)
async def create_project(
    payload: ProjectCreate,
    context: ContextDep,
    idempotency_key: IdempotencyDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[ProjectResource]:
    resource = await gateway.create_project(context, payload, idempotency_key)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.get(
    "/projects/{project_id}",
    operation_id="getProject",
    response_model=DataEnvelope[ProjectResource],
    responses=problem_responses(),
    tags=["projects"],
)
async def get_project(
    project_id: UUID,
    context: ContextDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[ProjectResource]:
    resource = await gateway.get_project(context, project_id)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.patch(
    "/projects/{project_id}",
    operation_id="updateProject",
    response_model=DataEnvelope[ProjectResource],
    responses=problem_responses(),
    tags=["projects"],
)
async def update_project(
    project_id: UUID,
    payload: ProjectPatch,
    context: ContextDep,
    expected_version: IfMatchDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[ProjectResource]:
    resource = await gateway.update_project(
        context,
        project_id,
        payload,
        expected_version,
    )
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.delete(
    "/projects/{project_id}",
    operation_id="archiveProject",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(),
    tags=["projects"],
)
async def archive_project(
    project_id: UUID,
    context: ContextDep,
    expected_version: IfMatchDep,
    gateway: GatewayDep,
) -> Response:
    await gateway.archive_project(context, project_id, expected_version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}:restore",
    operation_id="restoreProject",
    response_model=DataEnvelope[ProjectResource],
    responses=problem_responses(),
    tags=["projects"],
)
async def restore_project(
    project_id: UUID,
    context: ContextDep,
    expected_version: IfMatchDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[ProjectResource]:
    resource = await gateway.restore_project(context, project_id, expected_version)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.get(
    "/projects/{project_id}/brief/versions",
    operation_id="listProjectBriefVersions",
    response_model=CollectionEnvelope[ProjectBriefVersionResource],
    responses=problem_responses(),
    tags=["projects"],
)
async def list_project_brief_versions(
    project_id: UUID,
    context: ContextDep,
    gateway: GatewayDep,
) -> CollectionEnvelope[ProjectBriefVersionResource]:
    resources = await gateway.list_project_brief_versions(context, project_id)
    return CollectionEnvelope(
        data=resources,
        meta=PageMeta(request_id=context.request_id, next_cursor=None, has_more=False),
    )


@router.get(
    "/assets",
    operation_id="listAssets",
    response_model=CollectionEnvelope[AssetResource],
    responses=problem_responses(),
    tags=["assets"],
)
async def list_assets(
    context: ContextDep,
    page: PageDep,
    gateway: GatewayDep,
    project_id: Annotated[UUID | None, Query()] = None,
) -> CollectionEnvelope[AssetResource]:
    result = await gateway.list_assets(context, project_id, page)
    return CollectionEnvelope(data=result.items, meta=_page_meta(context, result))


@router.post(
    "/assets",
    operation_id="createAsset",
    response_model=DataEnvelope[AssetResource],
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(),
    tags=["assets"],
)
async def create_asset(
    payload: AssetCreate,
    context: ContextDep,
    idempotency_key: IdempotencyDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[AssetResource]:
    resource = await gateway.create_asset(context, payload, idempotency_key)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.get(
    "/assets/{asset_id}",
    operation_id="getAsset",
    response_model=DataEnvelope[AssetResource],
    responses=problem_responses(),
    tags=["assets"],
)
async def get_asset(
    asset_id: UUID,
    context: ContextDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[AssetResource]:
    resource = await gateway.get_asset(context, asset_id)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.get(
    "/artifacts/{artifact_id}",
    operation_id="getArtifact",
    response_model=DataEnvelope[ArtifactResource],
    responses=problem_responses(),
    tags=["artifacts"],
)
async def get_artifact(
    artifact_id: UUID,
    context: ContextDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[ArtifactResource]:
    resource = await gateway.get_artifact(context, artifact_id)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.get(
    "/artifacts/{artifact_id}/versions",
    operation_id="listArtifactVersions",
    response_model=CollectionEnvelope[ArtifactVersionResource],
    responses=problem_responses(),
    tags=["artifacts"],
)
async def list_artifact_versions(
    artifact_id: UUID,
    context: ContextDep,
    page: PageDep,
    gateway: GatewayDep,
) -> CollectionEnvelope[ArtifactVersionResource]:
    result = await gateway.list_artifact_versions(context, artifact_id, page)
    return CollectionEnvelope(data=result.items, meta=_page_meta(context, result))


@router.post(
    "/artifacts/{artifact_id}/versions",
    operation_id="createArtifactVersion",
    response_model=DataEnvelope[ArtifactVersionResource],
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(),
    tags=["artifacts"],
)
async def create_artifact_version(
    artifact_id: UUID,
    payload: ArtifactVersionCreate,
    context: ContextDep,
    idempotency_key: IdempotencyDep,
    gateway: GatewayDep,
) -> DataEnvelope[ArtifactVersionResource]:
    resource = await gateway.create_artifact_version(
        context,
        artifact_id,
        payload,
        idempotency_key,
    )
    return DataEnvelope(data=resource, meta=_meta(context))


@router.post(
    "/agent-runs",
    operation_id="createAgentRun",
    response_model=DataEnvelope[AgentRunResource],
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(),
    tags=["agent-runs"],
)
async def create_agent_run(
    payload: AgentRunCreate,
    context: ContextDep,
    idempotency_key: IdempotencyDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[AgentRunResource]:
    resource = await gateway.create_agent_run(context, payload, idempotency_key)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.get(
    "/agent-runs/{agent_run_id}",
    operation_id="getAgentRun",
    response_model=DataEnvelope[AgentRunResource],
    responses=problem_responses(),
    tags=["agent-runs"],
)
async def get_agent_run(
    agent_run_id: UUID,
    context: ContextDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[AgentRunResource]:
    resource = await gateway.get_agent_run(context, agent_run_id)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.post(
    "/agent-runs/{agent_run_id}:cancel",
    operation_id="cancelAgentRun",
    response_model=DataEnvelope[AgentRunResource],
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(),
    tags=["agent-runs"],
)
async def cancel_agent_run(
    agent_run_id: UUID,
    context: ContextDep,
    idempotency_key: IdempotencyDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[AgentRunResource]:
    resource = await gateway.cancel_agent_run(context, agent_run_id, idempotency_key)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.post(
    "/agent-runs/{agent_run_id}:resume",
    operation_id="resumeAgentRun",
    response_model=DataEnvelope[AgentRunResource],
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(),
    tags=["agent-runs"],
)
async def resume_agent_run(
    agent_run_id: UUID,
    payload: AgentRunResumeRequest,
    context: ContextDep,
    idempotency_key: IdempotencyDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[AgentRunResource]:
    resource = await gateway.resume_agent_run(
        context,
        agent_run_id,
        payload,
        idempotency_key,
    )
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.get(
    "/tasks/{task_id}",
    operation_id="getTask",
    response_model=DataEnvelope[TaskResource],
    responses=problem_responses(),
    tags=["tasks"],
)
async def get_task(
    task_id: UUID,
    context: ContextDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[TaskResource]:
    resource = await gateway.get_task(context, task_id)
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.post(
    "/generations",
    operation_id="createGeneration",
    response_model=DataEnvelope[GenerationResource],
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(),
    tags=["generations"],
)
async def create_generation(
    payload: GenerationCreate,
    context: ContextDep,
    idempotency_key: IdempotencyDep,
    gateway: GatewayDep,
) -> DataEnvelope[GenerationResource]:
    resource = await gateway.create_generation(context, payload, idempotency_key)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.get(
    "/generations/{generation_id}",
    operation_id="getGeneration",
    response_model=DataEnvelope[GenerationResource],
    responses=problem_responses(),
    tags=["generations"],
)
async def get_generation(
    generation_id: UUID,
    context: ContextDep,
    gateway: GatewayDep,
) -> DataEnvelope[GenerationResource]:
    resource = await gateway.get_generation(context, generation_id)
    return DataEnvelope(data=resource, meta=_meta(context))


@router.post(
    "/approvals/{approval_id}:decide",
    operation_id="decideApproval",
    response_model=DataEnvelope[ApprovalResource],
    responses=problem_responses(),
    tags=["approvals"],
)
async def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    context: ContextDep,
    idempotency_key: IdempotencyDep,
    expected_version: IfMatchDep,
    gateway: GatewayDep,
    response: Response,
) -> DataEnvelope[ApprovalResource]:
    resource = await gateway.decide_approval(
        context,
        approval_id,
        payload,
        idempotency_key,
        expected_version,
    )
    _set_version_etag(response, resource.version)
    return DataEnvelope(data=resource, meta=_meta(context))


PROBLEM_DETAILS_SCHEMA = ProblemDetails
