from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request

from .brand_registry_schemas import BrandCreateRequest, BrandPage, BrandPatchRequest, BrandResponse
from .errors import ApiProblem


class BrandRegistryService(Protocol):
    def list_brands(
        self,
        *,
        organization_id: UUID,
        limit: int,
        query: str | None,
    ) -> BrandPage: ...

    def create_brand(
        self,
        *,
        organization_id: UUID,
        request: BrandCreateRequest,
    ) -> BrandResponse: ...

    def get_brand(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
    ) -> BrandResponse: ...

    def patch_brand(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        request: BrandPatchRequest,
        expected_version: int,
    ) -> BrandResponse: ...


class BrandRegistryServiceFactory(Protocol):
    def __call__(self) -> AbstractContextManager[BrandRegistryService]: ...


def get_brand_registry_service(
    request: Request,
) -> Generator[BrandRegistryService, None, None]:
    factory = getattr(request.app.state, "brand_registry_service_factory", None)
    if factory is None:
        raise ApiProblem(
            status=503,
            code="brand_registry_service_not_composed",
            title="Brand registry unavailable",
            detail="The request-scoped Brand registry service factory is not composed in this deployment.",
        )
    with factory() as service:
        yield service


BrandRegistryServiceDependency = Annotated[
    BrandRegistryService,
    Depends(get_brand_registry_service),
]
