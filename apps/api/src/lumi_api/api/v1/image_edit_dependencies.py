from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from lumi_api.image_edit import ImageEditApplicationService

from .errors import ApiProblem


def get_image_edit_service() -> ImageEditApplicationService:
    raise ApiProblem(
        status=503,
        code="image_edit_service_not_configured",
        title="Image Edit unavailable",
        detail=(
            "NODE-47 Image Edit is installed but no production runtime "
            "adapter is configured."
        ),
    )


ImageEditServiceDependency = Annotated[
    ImageEditApplicationService,
    Depends(get_image_edit_service),
]
