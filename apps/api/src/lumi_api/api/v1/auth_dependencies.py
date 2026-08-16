from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from lumi_api.auth import AuthService

from .errors import ApiProblem


def get_auth_service() -> AuthService:
    raise ApiProblem(
        status=503,
        code="auth_service_not_configured",
        title="Authentication service unavailable",
        detail="NODE-16 auth contract is installed but no runtime auth store is configured.",
    )


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
