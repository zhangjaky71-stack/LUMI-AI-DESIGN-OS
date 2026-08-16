from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from lumi_api.assets.api import AssetApiService

from .errors import ApiProblem


def get_asset_api_service() -> AssetApiService:
    raise ApiProblem(
        status=503,
        code="asset_service_not_configured",
        title="Asset storage service unavailable",
        detail="The Asset Storage contract is installed but no runtime adapter is configured.",
    )


AssetServiceDependency = Annotated[AssetApiService, Depends(get_asset_api_service)]
