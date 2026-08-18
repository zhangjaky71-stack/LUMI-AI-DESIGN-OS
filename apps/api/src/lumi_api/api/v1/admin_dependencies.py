from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request

from lumi_api.admin import PlatformAdminForbidden, PlatformAdminService

from .errors import ApiProblem


class PlatformAdminServiceFactory(Protocol):
    def __call__(self, user_id: UUID) -> AbstractContextManager[PlatformAdminService]: ...


def get_platform_admin_factory(request: Request) -> PlatformAdminServiceFactory:
    factory = getattr(request.app.state, "platform_admin_service_factory", None)
    if factory is None:
        raise ApiProblem(status=503, code="platform_admin_service_not_composed", title="Platform admin unavailable", detail="The NODE-64 platform admin service is not composed in this deployment.")
    return factory


def get_platform_admin_service(
    request: Request,
    factory: Annotated[PlatformAdminServiceFactory, Depends(get_platform_admin_factory)],
) -> Generator[PlatformAdminService, None, None]:
    user_id = getattr(request.state, "platform_admin_user_id", None)
    if not isinstance(user_id, UUID):
        raise ApiProblem(status=401, code="platform_admin_identity_missing", title="Platform admin identity missing", detail="The request has not established a platform admin user identity.")
    try:
        with factory(user_id) as service:
            yield service
    except PlatformAdminForbidden as exc:
        raise ApiProblem(status=403, code=exc.code.casefold(), title="Platform admin access denied", detail=str(exc)) from exc


PlatformAdminServiceDependency = Annotated[PlatformAdminService, Depends(get_platform_admin_service)]
