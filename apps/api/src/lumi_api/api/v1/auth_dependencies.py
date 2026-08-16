from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from lumi_api.auth import AuthService, SessionCookiePolicy

from .errors import ApiProblem


@dataclass(frozen=True, slots=True)
class AuthHttpSettings:
    environment: str = "production"
    allowed_origins: frozenset[str] = frozenset()

    @property
    def cookie_policy(self) -> SessionCookiePolicy:
        return SessionCookiePolicy.for_environment(self.environment)


def get_auth_service() -> AuthService:
    raise ApiProblem(
        status=503,
        code="auth_service_not_configured",
        title="Authentication service unavailable",
        detail="NODE-16 auth contract is installed but no runtime auth store is configured.",
    )


def get_auth_http_settings() -> AuthHttpSettings:
    return AuthHttpSettings()


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
AuthHttpSettingsDependency = Annotated[AuthHttpSettings, Depends(get_auth_http_settings)]
