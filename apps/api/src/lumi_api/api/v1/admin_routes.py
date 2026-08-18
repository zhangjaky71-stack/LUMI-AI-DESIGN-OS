from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from lumi_api.admin import PlatformAdminConflict, PlatformAdminForbidden, PlatformAdminNotFound, PlatformAdminUnavailable

from .admin_dependencies import PlatformAdminServiceDependency
from .admin_schemas import FeatureFlagRequest, ProviderOverrideRequest, ReasonRequest, RegistryPromotionRequest
from .common import ProblemDetail
from .errors import ApiProblem

router = APIRouter(prefix="/api/v1/admin", tags=["platform-admin"])
_ERROR_RESPONSES = {400: {"model": ProblemDetail}, 403: {"model": ProblemDetail}, 404: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 503: {"model": ProblemDetail}}


def _problem(exc: Exception) -> ApiProblem:
    if isinstance(exc, PlatformAdminForbidden):
        return ApiProblem(status=403, code=exc.code.casefold(), title="Platform admin forbidden", detail=str(exc))
    if isinstance(exc, PlatformAdminNotFound):
        return ApiProblem(status=404, code=exc.code.casefold(), title="Admin resource not found", detail=str(exc))
    if isinstance(exc, PlatformAdminConflict):
        return ApiProblem(status=409, code=exc.code.casefold(), title="Admin state conflict", detail=str(exc))
    if isinstance(exc, PlatformAdminUnavailable):
        return ApiProblem(status=503, code=exc.code.casefold(), title="Admin operation unavailable", detail=str(exc))
    if isinstance(exc, ValueError):
        return ApiProblem(status=422, code="platform_admin_request_invalid", title="Invalid admin request", detail=str(exc))
    raise exc


@router.get("/me", responses=_ERROR_RESPONSES)
def admin_me(service: PlatformAdminServiceDependency):
    return service.principal


@router.get("/dashboard", responses=_ERROR_RESPONSES)
def dashboard(service: PlatformAdminServiceDependency):
    try:
        return service.dashboard()
    except Exception as exc:
        raise _problem(exc) from exc


@router.get("/runs/failing", responses=_ERROR_RESPONSES)
def failing_runs(service: PlatformAdminServiceDependency, limit: Annotated[int, Query(ge=1, le=200)] = 100):
    try:
        return service.failing_runs(limit=limit)
    except Exception as exc:
        raise _problem(exc) from exc


@router.get("/dlq", responses=_ERROR_RESPONSES)
def dead_letters(service: PlatformAdminServiceDependency, limit: Annotated[int, Query(ge=1, le=200)] = 100):
    try:
        return service.dead_letters(limit=limit)
    except Exception as exc:
        raise _problem(exc) from exc


@router.post("/dlq/{dead_letter_id}/replay", responses=_ERROR_RESPONSES)
def replay_dead_letter(dead_letter_id: UUID, body: ReasonRequest, service: PlatformAdminServiceDependency):
    try:
        service.replay_dead_letter(dead_letter_id=dead_letter_id, reason=body.reason)
        return {"status": "replayed"}
    except Exception as exc:
        raise _problem(exc) from exc


@router.post("/dlq/{dead_letter_id}/discard", responses=_ERROR_RESPONSES)
def discard_dead_letter(dead_letter_id: UUID, body: ReasonRequest, service: PlatformAdminServiceDependency):
    try:
        service.discard_dead_letter(dead_letter_id=dead_letter_id, reason=body.reason)
        return {"status": "discarded"}
    except Exception as exc:
        raise _problem(exc) from exc


@router.get("/providers", responses=_ERROR_RESPONSES)
def providers(service: PlatformAdminServiceDependency, limit: Annotated[int, Query(ge=1, le=200)] = 100):
    try:
        return service.providers(limit=limit)
    except Exception as exc:
        raise _problem(exc) from exc


@router.post("/providers/override", responses=_ERROR_RESPONSES)
def provider_override(body: ProviderOverrideRequest, service: PlatformAdminServiceDependency):
    try:
        override_id = service.provider_override(provider=body.provider, model=body.model, capability=body.capability, action=body.action, reason=body.reason, expires_at=body.expires_at)
        return {"id": str(override_id), "status": "recorded"}
    except Exception as exc:
        raise _problem(exc) from exc


@router.get("/feature-flags", responses=_ERROR_RESPONSES)
def feature_flags(service: PlatformAdminServiceDependency):
    try:
        return service.feature_flags()
    except Exception as exc:
        raise _problem(exc) from exc


@router.put("/feature-flags", responses=_ERROR_RESPONSES)
def upsert_feature_flag(body: FeatureFlagRequest, service: PlatformAdminServiceDependency):
    try:
        return service.upsert_feature_flag(flag_key=body.flag_key, scope=body.scope, target_id=body.target_id, value=body.value, owner=body.owner, reason=body.reason, expires_at=body.expires_at)
    except Exception as exc:
        raise _problem(exc) from exc


@router.post("/registry/promote", responses=_ERROR_RESPONSES)
def promote_registry(body: RegistryPromotionRequest, service: PlatformAdminServiceDependency):
    try:
        service.promote_registry_version(registry_kind=body.registry_kind, key=body.key, version=body.version, reason=body.reason)
        return {"status": "promoted"}
    except Exception as exc:
        raise _problem(exc) from exc
