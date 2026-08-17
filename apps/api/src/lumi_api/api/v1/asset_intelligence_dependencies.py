from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from lumi_asset_intelligence import AssetIntelligenceService

from .errors import ApiProblem


def get_asset_intelligence_service() -> AssetIntelligenceService:
    raise ApiProblem(
        status=503,
        code="asset_intelligence_service_not_configured",
        title="Asset Intelligence unavailable",
        detail="NODE-45 Asset Intelligence is installed but no runtime adapter is configured.",
    )


AssetIntelligenceServiceDependency = Annotated[
    AssetIntelligenceService,
    Depends(get_asset_intelligence_service),
]
