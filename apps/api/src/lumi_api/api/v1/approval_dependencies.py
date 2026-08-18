from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request

from lumi_api.approvals import ApprovalService

from .errors import ApiProblem
from .headers import OrganizationId


class ApprovalServiceFactory(Protocol):
    def __call__(self, organization_id: UUID) -> AbstractContextManager[ApprovalService]: ...


def get_approval_service(
    request: Request,
    organization_id: OrganizationId,
) -> Generator[ApprovalService, None, None]:
    factory = getattr(request.app.state, "approval_service_factory", None)
    if factory is None:
        raise ApiProblem(
            status=503,
            code="approval_service_not_composed",
            title="Approval service unavailable",
            detail=(
                "NODE-62 Approval Engine contracts are installed but the request-scoped "
                "PostgreSQL service factory is not composed in this deployment."
            ),
        )
    with factory(organization_id) as service:
        yield service


ApprovalServiceDependency = Annotated[ApprovalService, Depends(get_approval_service)]
