from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from lumi_api.artifact_engine import ArtifactEngineService

from .errors import ApiProblem
from .headers import OrganizationId

ArtifactEngineServiceFactory = Callable[[UUID], ArtifactEngineService]


def get_artifact_engine_service(
    request: Request,
    organization_id: OrganizationId,
) -> ArtifactEngineService:
    factory = getattr(request.app.state, "artifact_engine_service_factory", None)
    if callable(factory):
        return factory(organization_id)
    service = getattr(request.app.state, "artifact_engine_service", None)
    if isinstance(service, ArtifactEngineService):
        return service
    raise ApiProblem(
        status=503,
        code="artifact_engine_not_configured",
        title="Artifact Engine unavailable",
        detail="NODE-42 Artifact Engine is installed but no runtime adapter is configured.",
    )


ArtifactEngineServiceDependency = Annotated[
    ArtifactEngineService,
    Depends(get_artifact_engine_service),
]
