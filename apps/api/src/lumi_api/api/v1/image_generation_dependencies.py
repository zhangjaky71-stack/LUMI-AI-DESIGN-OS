from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from lumi_api.image_generation.application import ImageGenerationApplicationService

from .errors import ApiProblem


def get_image_generation_service() -> ImageGenerationApplicationService:
    raise ApiProblem(
        status=503,
        code="image_generation_service_not_configured",
        title="Image Generation unavailable",
        detail="NODE-46 Image Generation is installed but no runtime adapter is configured.",
    )


ImageGenerationServiceDependency = Annotated[
    ImageGenerationApplicationService,
    Depends(get_image_generation_service),
]
