from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from lumi_api.governance import GovernanceService

from .errors import ApiProblem


def get_governance_service(request: Request) -> Iterator[GovernanceService]:
    factory = getattr(request.app.state, "governance_service_factory", None)
    if factory is None:
        raise ApiProblem(
            status=503,
            code="governance_service_not_composed",
            title="Governance service unavailable",
            detail="The production Governance service factory is not composed.",
        )
    with factory() as service:
        yield service


GovernanceServiceDependency = Annotated[GovernanceService, Depends(get_governance_service)]
