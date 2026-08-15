from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from .errors import ApiProblem
from .ports import ApiV1Service


def get_api_v1_service() -> ApiV1Service:
    raise ApiProblem(
        status=503,
        code="api_service_not_configured",
        title="API service unavailable",
        detail=(
            "The v1 contract is installed but its application service adapter "
            "has not been configured."
        ),
    )


ApiServiceDependency = Annotated[ApiV1Service, Depends(get_api_v1_service)]
