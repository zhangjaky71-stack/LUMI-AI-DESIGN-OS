from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from .context import RequestContext, get_request_context
from .contracts import (
    CollectionEnvelope,
    CostSummaryResource,
    DataEnvelope,
    PageMeta,
    ResponseMeta,
    UsageSummaryResource,
)
from .errors import ApiProblem, problem_responses
from .services import ApiV1Gateway, get_api_v1_gateway

cost_router = APIRouter(prefix="/api/v1")

ContextDep = Annotated[RequestContext, Depends(get_request_context)]
GatewayDep = Annotated[ApiV1Gateway, Depends(get_api_v1_gateway)]


def _validate_range(from_time: datetime, to_time: datetime) -> None:
    if from_time.tzinfo is None or to_time.tzinfo is None:
        raise ApiProblem(
            status=400,
            code="COST_TIMEZONE_REQUIRED",
            title="Timezone required",
            detail="Cost and usage time ranges must include an explicit timezone.",
        )
    if from_time >= to_time:
        raise ApiProblem(
            status=400,
            code="COST_TIME_RANGE_INVALID",
            title="Invalid cost time range",
            detail="from_time must be earlier than to_time.",
        )


@cost_router.get(
    "/usage",
    operation_id="getUsageSummary",
    response_model=CollectionEnvelope[UsageSummaryResource],
    responses=problem_responses(),
    tags=["costs"],
)
async def get_usage_summary(
    context: ContextDep,
    gateway: GatewayDep,
    from_time: Annotated[datetime, Query()],
    to_time: Annotated[datetime, Query()],
    project_id: Annotated[UUID | None, Query()] = None,
) -> CollectionEnvelope[UsageSummaryResource]:
    _validate_range(from_time, to_time)
    resources = await gateway.list_usage_summary(
        context,
        from_time=from_time,
        to_time=to_time,
        project_id=project_id,
    )
    return CollectionEnvelope(
        data=resources,
        meta=PageMeta(
            request_id=context.request_id,
            next_cursor=None,
            has_more=False,
        ),
    )


@cost_router.get(
    "/costs/summary",
    operation_id="getCostSummary",
    response_model=DataEnvelope[CostSummaryResource],
    responses=problem_responses(),
    tags=["costs"],
)
async def get_cost_summary(
    context: ContextDep,
    gateway: GatewayDep,
    from_time: Annotated[datetime, Query()],
    to_time: Annotated[datetime, Query()],
) -> DataEnvelope[CostSummaryResource]:
    _validate_range(from_time, to_time)
    resource = await gateway.get_cost_summary(
        context,
        from_time=from_time,
        to_time=to_time,
        project_id=None,
    )
    return DataEnvelope(data=resource, meta=ResponseMeta(request_id=context.request_id))


@cost_router.get(
    "/projects/{project_id}/costs",
    operation_id="getProjectCostSummary",
    response_model=DataEnvelope[CostSummaryResource],
    responses=problem_responses(),
    tags=["costs"],
)
async def get_project_cost_summary(
    project_id: UUID,
    context: ContextDep,
    gateway: GatewayDep,
    from_time: Annotated[datetime, Query()],
    to_time: Annotated[datetime, Query()],
) -> DataEnvelope[CostSummaryResource]:
    _validate_range(from_time, to_time)
    resource = await gateway.get_cost_summary(
        context,
        from_time=from_time,
        to_time=to_time,
        project_id=project_id,
    )
    return DataEnvelope(data=resource, meta=ResponseMeta(request_id=context.request_id))
