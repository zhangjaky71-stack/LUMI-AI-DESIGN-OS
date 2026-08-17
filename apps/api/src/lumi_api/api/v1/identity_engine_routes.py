from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, status

from lumi_api.identity_engine.contracts import (
    CalibrationReport,
    IdentityReferenceSet,
    IdentityValidationResult,
)
from lumi_api.identity_engine.repository import IdentityNotFound
from lumi_api.identity_engine.service import IdentityPrivacyDenied

from .common import ProblemDetail
from .errors import ApiProblem
from .headers import OrganizationId
from .identity_engine_dependencies import IdentityServiceDependency
from .identity_engine_schemas import (
    CalibrateIdentityRequest,
    CompareIdentityRequest,
    CreateIdentityReferenceSetRequest,
    CreateIdentityVersionRequest,
    ValidateIdentityRequest,
)

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
            detail="Identity reference changes require an authenticated actor.",
        )
    return str(actor_id)


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, IdentityNotFound):
        return ApiProblem(
            status=404,
            code=exc.code,
            title="Identity reference set not found",
            detail=str(exc),
        )
    if isinstance(exc, IdentityPrivacyDenied):
        return ApiProblem(
            status=403,
            code=exc.code,
            title="Identity privacy policy denied",
            detail=str(exc),
        )
    raise exc


@router.post(
    "/identity/reference-sets",
    response_model=IdentityReferenceSet,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["identity"],
)
def create_reference_set(
    body: CreateIdentityReferenceSetRequest,
    request: Request,
    organization_id: OrganizationId,
    service: IdentityServiceDependency,
) -> IdentityReferenceSet:
    try:
        return service.create_reference_set(
            organization_id=organization_id,
            project_id=body.project_id,
            brand_id=body.brand_id,
            identity_type=body.identity_type,
            name=body.name,
            canonical_asset_ids=body.canonical_asset_ids,
            reference_views=body.reference_views,
            threshold_profile=body.threshold_profile,
            notes=body.notes,
            created_at=datetime.now(UTC),
            created_by=_actor_id(request),
            privacy_authorized=body.privacy_authorized,
        )
    except (IdentityNotFound, IdentityPrivacyDenied) as exc:
        raise _translate(exc) from exc


@router.post(
    "/identity/reference-sets/{identity_id}/versions",
    response_model=IdentityReferenceSet,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["identity"],
)
def create_reference_version(
    identity_id: UUID,
    body: CreateIdentityVersionRequest,
    request: Request,
    organization_id: OrganizationId,
    service: IdentityServiceDependency,
) -> IdentityReferenceSet:
    try:
        return service.create_version(
            organization_id=organization_id,
            identity_id=identity_id,
            canonical_asset_ids=body.canonical_asset_ids,
            reference_views=body.reference_views,
            threshold_profile=body.threshold_profile,
            notes=body.notes,
            created_at=datetime.now(UTC),
            created_by=_actor_id(request),
        )
    except (IdentityNotFound, IdentityPrivacyDenied) as exc:
        raise _translate(exc) from exc


@router.get(
    "/identity/reference-sets/{identity_id}",
    response_model=IdentityReferenceSet,
    responses=_ERROR_RESPONSES,
    tags=["identity"],
)
def get_reference_set(
    identity_id: UUID,
    organization_id: OrganizationId,
    service: IdentityServiceDependency,
) -> IdentityReferenceSet:
    try:
        return service.repository.get_latest(organization_id, identity_id)
    except IdentityNotFound as exc:
        raise _translate(exc) from exc


@router.post(
    "/identity/reference-sets/{identity_id}/validate",
    response_model=IdentityValidationResult,
    responses=_ERROR_RESPONSES,
    tags=["identity"],
)
def validate_identity(
    identity_id: UUID,
    body: ValidateIdentityRequest,
    organization_id: OrganizationId,
    service: IdentityServiceDependency,
) -> IdentityValidationResult:
    try:
        return service.validate(
            organization_id=organization_id,
            identity_id=identity_id,
            candidate=body.candidate,
            profile=body.threshold_profile,
        )
    except IdentityNotFound as exc:
        raise _translate(exc) from exc


@router.post(
    "/identity/compare",
    response_model=IdentityValidationResult,
    responses=_ERROR_RESPONSES,
    tags=["identity"],
)
def compare_identity(
    body: CompareIdentityRequest,
    organization_id: OrganizationId,
    service: IdentityServiceDependency,
) -> IdentityValidationResult:
    try:
        return service.compare(
            organization_id=organization_id,
            a=body.a,
            b=body.b,
            identity_type=body.identity_type,
            profile=body.threshold_profile,
            created_at=datetime.now(UTC),
        )
    except IdentityPrivacyDenied as exc:
        raise _translate(exc) from exc


@router.post(
    "/identity/calibration-reports",
    response_model=CalibrationReport,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["identity"],
)
def calibrate_identity(
    body: CalibrateIdentityRequest,
    organization_id: OrganizationId,
    service: IdentityServiceDependency,
) -> CalibrationReport:
    return service.calibrate(
        organization_id=organization_id,
        identity_type=body.identity_type,
        profile_key=body.profile_key,
        version=body.version,
        samples=body.samples,
        target_precision=body.target_precision,
        created_at=datetime.now(UTC),
    )
