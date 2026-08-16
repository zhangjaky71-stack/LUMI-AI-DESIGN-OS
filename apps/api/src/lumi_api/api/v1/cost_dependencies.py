from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends

from lumi_api.costs.read_service import PostgresCostReadService

from .errors import ApiProblem


def get_cost_read_service() -> PostgresCostReadService:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ApiProblem(
            status=503,
            code="cost_read_service_not_configured",
            title="Cost read service unavailable",
            detail="DATABASE_URL is not configured for the NODE-27 cost projection.",
        )
    return PostgresCostReadService(dsn)


CostReadDependency = Annotated[
    PostgresCostReadService,
    Depends(get_cost_read_service),
]
