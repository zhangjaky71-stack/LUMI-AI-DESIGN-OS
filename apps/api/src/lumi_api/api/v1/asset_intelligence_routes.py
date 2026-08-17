from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, status

from lumi_asset_intelligence import (
    AccessScope,
    AnalysisJob,
    AssetAnalysisRecord,
    AssetIndexVersion,
    AssetIntelligenceError,
    AssetIntelligenceNotFound,
    AssetSearchRequest,
    DuplicateEvidence,
    IndexBuildJob,
    IndexPromotionDecision,
    ResolverResult,
    SearchHit,
    UsageSignal,
)
from lumi_api.domain.ids import new_uuid7

from .asset_intelligence_dependencies import AssetIntelligenceServiceDependency
from .asset_intelligence_schemas import (
    ActivateAssetIndexRequest,
    AssetSearchBody,
    CreateAssetIndexRequest,
    DuplicateSearchRequest,
    UsageFeedbackRequest,
)
from .common import ProblemDetail
from .errors import ApiProblem
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1")

_ERROR_RESPONSES = {
    400: {"model": ProblemDetail},
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _actor_id(request: Request) -> str:
    context = getattr(request.state, "lumi_context", None)
    actor_id = getattr(context, "actor_id", None)
    if not actor_id:
        raise ApiProblem(
            status=401,
            code="authenticated_actor_required",
            title="Authenticated actor required",
            detail="Asset Intelligence changes require an authenticated actor.",
        )
    return str(actor_id)


def _scope(organization_id: UUID, body) -> AccessScope:
    return AccessScope(
        organization_id=organization_id,
        project_ids=body.project_ids,
        brand_ids=body.brand_ids,
        permission_tags=body.permission_tags,
        allowed_rights=body.allowed_rights,
        commercial_use=body.commercial_use,
    )


def _search_request(organization_id: UUID, body: AssetSearchBody) -> AssetSearchRequest:
    return AssetSearchRequest(
        scope=_scope(organization_id, body.scope),
        query=body.query,
        mode=body.mode,
        filters=body.filters,
        query_embedding=body.query_embedding,
        similar_to_asset_id=body.similar_to_asset_id,
        limit=body.limit,
    )


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, AssetIntelligenceNotFound):
        return ApiProblem(
            status=404,
            code=exc.code,
            title="Asset Intelligence resource not found",
            detail=str(exc),
        )
    if isinstance(exc, PermissionError):
        return ApiProblem(
            status=403,
            code="asset_intelligence_scope_denied",
            title="Asset Intelligence scope denied",
            detail=str(exc),
        )
    if isinstance(exc, AssetIntelligenceError):
        return ApiProblem(
            status=409,
            code="asset_intelligence_conflict",
            title="Asset Intelligence conflict",
            detail=str(exc),
        )
    if isinstance(exc, ValueError):
        return ApiProblem(
            status=422,
            code="asset_intelligence_invalid_request",
            title="Asset Intelligence request invalid",
            detail=str(exc),
        )
    raise exc


@router.post(
    "/asset-intelligence/indexes",
    response_model=AssetIndexVersion,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def create_index(
    body: CreateAssetIndexRequest,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> AssetIndexVersion:
    try:
        return service.create_index(
            organization_id=organization_id,
            analyzer_version=body.analyzer_version,
            created_at=datetime.now(UTC),
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/asset-intelligence/indexes/{index_id}/build",
    response_model=IndexBuildJob,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def build_index(
    index_id: UUID,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> IndexBuildJob:
    try:
        return service.schedule_index_build(
            organization_id=organization_id,
            index_id=index_id,
            requested_at=datetime.now(UTC),
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/asset-intelligence/indexes/{index_id}/activate",
    response_model=AssetIndexVersion,
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def activate_index(
    index_id: UUID,
    body: ActivateAssetIndexRequest,
    request: Request,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> AssetIndexVersion:
    try:
        comparison = service.compare_index_coverage(
            organization_id=organization_id,
            candidate_index_id=index_id,
        )
        decision = IndexPromotionDecision(
            comparison=comparison,
            approved=body.approved,
            approved_by=_actor_id(request),
            reason=body.reason,
        )
        return service.activate_index(
            organization_id=organization_id,
            index_id=index_id,
            decision=decision,
            activated_at=datetime.now(UTC),
            minimum_coverage_ratio=body.minimum_coverage_ratio,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/assets/{asset_id}/intelligence/analyze",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def analyze_asset(
    asset_id: UUID,
    index_id: UUID,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> AnalysisJob:
    try:
        return service.schedule_asset_analysis(
            organization_id=organization_id,
            asset_id=asset_id,
            index_id=index_id,
            requested_at=datetime.now(UTC),
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/assets/{asset_id}/intelligence",
    response_model=AssetAnalysisRecord,
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def get_asset_intelligence(
    asset_id: UUID,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> AssetAnalysisRecord:
    try:
        return service.get_active_analysis(
            organization_id=organization_id,
            asset_id=asset_id,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/asset-intelligence/search",
    response_model=tuple[SearchHit, ...],
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def search_assets(
    body: AssetSearchBody,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> tuple[SearchHit, ...]:
    try:
        return tuple(service.search(_search_request(organization_id, body)))
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/asset-intelligence/resolve",
    response_model=ResolverResult,
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def resolve_asset(
    body: AssetSearchBody,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> ResolverResult:
    try:
        return service.resolve_for_agent(_search_request(organization_id, body))
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/assets/{asset_id}/duplicates",
    response_model=tuple[DuplicateEvidence, ...],
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def find_duplicates(
    asset_id: UUID,
    body: DuplicateSearchRequest,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> tuple[DuplicateEvidence, ...]:
    try:
        return service.find_duplicates(
            scope=_scope(organization_id, body.scope),
            source_asset_id=asset_id,
            policy=body.policy,
            filters=body.filters,
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/assets/{asset_id}/usage-feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERROR_RESPONSES,
    tags=["asset-intelligence"],
)
def usage_feedback(
    asset_id: UUID,
    body: UsageFeedbackRequest,
    request: Request,
    organization_id: OrganizationId,
    service: AssetIntelligenceServiceDependency,
) -> None:
    signal = UsageSignal(
        id=new_uuid7(),
        organization_id=organization_id,
        asset_id=asset_id,
        signal=body.signal,
        occurred_at=body.occurred_at or datetime.now(UTC),
        project_id=body.project_id,
        actor_id=_actor_id(request),
        training_authorization_granted=False,
    )
    try:
        service.record_usage_signal(signal)
    except Exception as exc:
        raise _translate(exc) from exc
