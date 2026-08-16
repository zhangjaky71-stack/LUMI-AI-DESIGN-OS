from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from .cost_dependencies import CostReadDependency
from .cost_schemas import CostSummaryResponse, UsageSummaryResponse
from .errors import ApiProblem
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1/costs", tags=["costs"])


@router.get("/summary", response_model=CostSummaryResponse)
async def cost_summary(
    organization_id: OrganizationId,
    service: CostReadDependency,
    from_time: Annotated[datetime, Query(alias="from")],
    to_time: Annotated[datetime, Query(alias="to")],
    project_id: UUID | None = None,
    currency: Annotated[str, Query(pattern=r"^[A-Z]{3}$")] = "USD",
) -> CostSummaryResponse:
    try:
        data = await service.summary(
            organization_id=organization_id,
            from_time=from_time,
            to_time=to_time,
            project_id=project_id,
            currency=currency,
        )
    except ValueError as exc:
        raise ApiProblem(
            status=400,
            code="invalid_cost_range",
            title="Invalid cost query range",
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        if str(exc) != "COST_ASYNCPG_DEPENDENCY_NOT_INSTALLED":
            raise
        raise ApiProblem(
            status=503,
            code="cost_runtime_dependency_missing",
            title="Cost service unavailable",
            detail="The PostgreSQL runtime dependency is not installed.",
        ) from exc
    return CostSummaryResponse.model_validate(data)


@router.get("/usage", response_model=UsageSummaryResponse)
async def usage_summary(
    organization_id: OrganizationId,
    service: CostReadDependency,
    from_time: Annotated[datetime, Query(alias="from")],
    to_time: Annotated[datetime, Query(alias="to")],
    project_id: UUID | None = None,
) -> UsageSummaryResponse:
    try:
        rows = await service.usage(
            organization_id=organization_id,
            from_time=from_time,
            to_time=to_time,
            project_id=project_id,
        )
    except ValueError as exc:
        raise ApiProblem(
            status=400,
            code="invalid_usage_range",
            title="Invalid usage query range",
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        if str(exc) != "COST_ASYNCPG_DEPENDENCY_NOT_INSTALLED":
            raise
        raise ApiProblem(
            status=503,
            code="cost_runtime_dependency_missing",
            title="Cost service unavailable",
            detail="The PostgreSQL runtime dependency is not installed.",
        ) from exc
    return UsageSummaryResponse.model_validate({"items": list(rows)})
