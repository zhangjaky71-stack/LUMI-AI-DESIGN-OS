from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request

from lumi_api.billing import BillingService, PaymentEventStatus

from .errors import ApiProblem
from .headers import OrganizationId


class BillingServiceFactory(Protocol):
    def __call__(self, organization_id: UUID) -> AbstractContextManager[BillingService]: ...

    def handle_webhook(self, *, body: bytes, signature: str) -> PaymentEventStatus: ...


def get_billing_factory(request: Request) -> BillingServiceFactory:
    factory = getattr(request.app.state, "billing_service_factory", None)
    if factory is None:
        raise ApiProblem(
            status=503,
            code="billing_service_not_composed",
            title="Billing service unavailable",
            detail=(
                "NODE-63 Billing contracts are installed but the request-scoped "
                "billing service factory is not composed in this deployment."
            ),
        )
    return factory


def get_billing_service(
    organization_id: OrganizationId,
    factory: Annotated[BillingServiceFactory, Depends(get_billing_factory)],
) -> Generator[BillingService, None, None]:
    with factory(organization_id) as service:
        yield service


BillingServiceDependency = Annotated[BillingService, Depends(get_billing_service)]
BillingFactoryDependency = Annotated[BillingServiceFactory, Depends(get_billing_factory)]
