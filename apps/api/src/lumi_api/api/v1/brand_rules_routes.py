from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from lumi_api.brand_rules.contracts import (
    BrandContext,
    BrandGuideProposal,
    BrandRuleSet,
    ComplianceResult,
)
from lumi_api.brand_rules.service import (
    BrandRuleConflict,
    BrandRuleNotFound,
    BrandRulePublicationDenied,
)

from .brand_rules_dependencies import BrandRuleServiceDependency
from .brand_rules_schemas import (
    BrandComplianceRequest,
    CreateBrandRuleSetRequest,
    CreateGuideProposalRequest,
    PublishGuideProposalRequest,
    ReviewGuideProposalRequest,
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
            detail="Brand rule publication and review require an authenticated actor.",
        )
    return str(actor_id)


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, BrandRuleNotFound):
        return ApiProblem(status=404, code=exc.code, title="Brand rule resource not found", detail=str(exc))
    if isinstance(exc, BrandRulePublicationDenied):
        return ApiProblem(status=403, code=exc.code, title="Brand rule publication denied", detail=str(exc))
    if isinstance(exc, BrandRuleConflict):
        return ApiProblem(status=409, code=exc.code, title="Brand rule state conflict", detail=str(exc))
    raise exc


@router.post(
    "/brands/{brand_id}/rule-sets",
    response_model=BrandRuleSet,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def create_rule_set(
    brand_id: UUID,
    body: CreateBrandRuleSetRequest,
    request: Request,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandRuleSet:
    try:
        return service.create_draft(
            organization_id=organization_id,
            brand_id=brand_id,
            source=body.source,
            token_set=body.token_set,
            asset_set=body.asset_set,
            rules=body.rules,
            voice=body.voice,
            visual_style=body.visual_style,
            created_by=_actor_id(request),
        )
    except (BrandRuleNotFound, BrandRulePublicationDenied, BrandRuleConflict) as exc:
        raise _translate(exc) from exc


@router.get(
    "/brands/{brand_id}/rule-sets/active",
    response_model=BrandRuleSet,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def get_active_rule_set(
    brand_id: UUID,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandRuleSet:
    try:
        return service.get_active_rule_set(
            organization_id=organization_id,
            brand_id=brand_id,
        )
    except BrandRuleNotFound as exc:
        raise _translate(exc) from exc


@router.get(
    "/brands/{brand_id}/rule-sets/{rule_set_id}",
    response_model=BrandRuleSet,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def get_rule_set(
    brand_id: UUID,
    rule_set_id: UUID,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandRuleSet:
    try:
        return service.get_rule_set(
            organization_id=organization_id,
            brand_id=brand_id,
            rule_set_id=rule_set_id,
        )
    except BrandRuleNotFound as exc:
        raise _translate(exc) from exc


@router.post(
    "/brands/{brand_id}/rule-sets/{rule_set_id}/publish",
    response_model=BrandRuleSet,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def publish_rule_set(
    brand_id: UUID,
    rule_set_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandRuleSet:
    try:
        return service.publish(
            organization_id=organization_id,
            brand_id=brand_id,
            rule_set_id=rule_set_id,
            actor_id=_actor_id(request),
        )
    except (BrandRuleNotFound, BrandRulePublicationDenied, BrandRuleConflict) as exc:
        raise _translate(exc) from exc


@router.get(
    "/brands/{brand_id}/context",
    response_model=BrandContext,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def get_brand_context(
    brand_id: UUID,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandContext:
    try:
        return service.get_context(organization_id=organization_id, brand_id=brand_id)
    except BrandRuleNotFound as exc:
        raise _translate(exc) from exc


@router.post(
    "/brands/{brand_id}/compliance",
    response_model=ComplianceResult,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def evaluate_brand_compliance(
    brand_id: UUID,
    body: BrandComplianceRequest,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> ComplianceResult:
    try:
        return service.compliance(
            organization_id=organization_id,
            brand_id=brand_id,
            observations=body.observations,
            rule_set_id=body.rule_set_id,
        )
    except BrandRuleNotFound as exc:
        raise _translate(exc) from exc


@router.post(
    "/brands/{brand_id}/guide-proposals",
    response_model=BrandGuideProposal,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def create_guide_proposal(
    brand_id: UUID,
    body: CreateGuideProposalRequest,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandGuideProposal:
    return service.create_guide_proposal(
        organization_id=organization_id,
        brand_id=brand_id,
        source_asset_id=body.source_asset_id,
        rules=body.rules,
        citations=body.citations,
    )


@router.get(
    "/brands/{brand_id}/guide-proposals/{proposal_id}",
    response_model=BrandGuideProposal,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def get_guide_proposal(
    brand_id: UUID,
    proposal_id: UUID,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandGuideProposal:
    try:
        return service.get_guide_proposal(
            organization_id=organization_id,
            brand_id=brand_id,
            proposal_id=proposal_id,
        )
    except BrandRuleNotFound as exc:
        raise _translate(exc) from exc


@router.post(
    "/brands/{brand_id}/guide-proposals/{proposal_id}/review",
    response_model=BrandGuideProposal,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def review_guide_proposal(
    brand_id: UUID,
    proposal_id: UUID,
    body: ReviewGuideProposalRequest,
    request: Request,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandGuideProposal:
    try:
        return service.review_guide_proposal(
            organization_id=organization_id,
            brand_id=brand_id,
            proposal_id=proposal_id,
            actor_id=_actor_id(request),
            approve=body.approve,
        )
    except (BrandRuleNotFound, BrandRuleConflict) as exc:
        raise _translate(exc) from exc


@router.post(
    "/brands/{brand_id}/guide-proposals/{proposal_id}/publish",
    response_model=BrandRuleSet,
    responses=_ERROR_RESPONSES,
    tags=["brand-rules"],
)
def publish_guide_proposal(
    brand_id: UUID,
    proposal_id: UUID,
    body: PublishGuideProposalRequest,
    request: Request,
    organization_id: OrganizationId,
    service: BrandRuleServiceDependency,
) -> BrandRuleSet:
    try:
        return service.publish_guide_proposal(
            organization_id=organization_id,
            brand_id=brand_id,
            proposal_id=proposal_id,
            token_set=body.token_set,
            asset_set=body.asset_set,
            voice=body.voice,
            visual_style=body.visual_style,
            actor_id=_actor_id(request),
        )
    except (BrandRuleNotFound, BrandRulePublicationDenied, BrandRuleConflict) as exc:
        raise _translate(exc) from exc
