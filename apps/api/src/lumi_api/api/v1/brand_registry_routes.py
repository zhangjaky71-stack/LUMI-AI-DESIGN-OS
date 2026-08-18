from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from .brand_registry_dependencies import BrandRegistryServiceDependency
from .brand_registry_schemas import BrandCreateRequest, BrandPage, BrandPatchRequest, BrandResponse
from .common import parse_if_match, version_etag
from .errors import ApiProblem
from .headers import IfMatch, OrganizationId

router = APIRouter(prefix="/api/v1/brands", tags=["brands"])


def _expected_version(if_match: str) -> int:
    try:
        return parse_if_match(if_match)
    except ValueError as exc:
        raise ApiProblem(
            status=400,
            code="invalid_if_match",
            title="Invalid If-Match header",
            detail=str(exc),
        ) from exc


def _version_headers(response: Response, version: int) -> None:
    response.headers["ETag"] = version_etag(version)
    response.headers["Cache-Control"] = "private, no-cache"


@router.get("", response_model=BrandPage)
def list_brands(
    organization_id: OrganizationId,
    service: BrandRegistryServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    query: Annotated[str | None, Query(alias="q", min_length=1, max_length=200)] = None,
) -> BrandPage:
    return service.list_brands(
        organization_id=organization_id,
        limit=limit,
        query=query,
    )


@router.post("", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
def create_brand(
    request: BrandCreateRequest,
    response: Response,
    organization_id: OrganizationId,
    service: BrandRegistryServiceDependency,
) -> BrandResponse:
    brand = service.create_brand(organization_id=organization_id, request=request)
    _version_headers(response, brand.version)
    response.headers["Location"] = f"/api/v1/brands/{brand.id}"
    return brand


@router.get("/{brand_id}", response_model=BrandResponse)
def get_brand(
    brand_id: UUID,
    response: Response,
    organization_id: OrganizationId,
    service: BrandRegistryServiceDependency,
) -> BrandResponse:
    brand = service.get_brand(organization_id=organization_id, brand_id=brand_id)
    _version_headers(response, brand.version)
    return brand


@router.patch("/{brand_id}", response_model=BrandResponse)
def patch_brand(
    brand_id: UUID,
    request: BrandPatchRequest,
    response: Response,
    organization_id: OrganizationId,
    if_match: IfMatch,
    service: BrandRegistryServiceDependency,
) -> BrandResponse:
    brand = service.patch_brand(
        organization_id=organization_id,
        brand_id=brand_id,
        request=request,
        expected_version=_expected_version(if_match),
    )
    _version_headers(response, brand.version)
    return brand
