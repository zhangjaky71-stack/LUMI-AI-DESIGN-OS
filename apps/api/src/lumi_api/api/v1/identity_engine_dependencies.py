from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from lumi_api.identity_engine.service import IdentityService

from .errors import ApiProblem


def get_identity_service() -> IdentityService:
    raise ApiProblem(
        status=503,
        code="identity_service_not_configured",
        title="Identity service unavailable",
        detail="NODE-44 Identity Engine is installed but no runtime adapter is configured.",
    )


IdentityServiceDependency = Annotated[IdentityService, Depends(get_identity_service)]
