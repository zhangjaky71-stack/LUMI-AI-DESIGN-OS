from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request

from lumi_api.collaboration.service import CollaborationService

from .errors import ApiProblem
from .headers import OrganizationId


class CollaborationServiceFactory(Protocol):
    def __call__(self, organization_id: UUID) -> AbstractContextManager[CollaborationService]: ...


def get_collaboration_service(
    request: Request,
    organization_id: OrganizationId,
) -> Generator[CollaborationService, None, None]:
    factory = getattr(request.app.state, "collaboration_service_factory", None)
    if factory is None:
        raise ApiProblem(
            status=503,
            code="collaboration_service_not_composed",
            title="Collaboration service unavailable",
            detail=(
                "NODE-61 collaboration contracts are installed but the request-scoped "
                "PostgreSQL/presence service factory is not composed in this deployment."
            ),
        )
    with factory(organization_id) as service:
        yield service


CollaborationServiceDependency = Annotated[
    CollaborationService,
    Depends(get_collaboration_service),
]
