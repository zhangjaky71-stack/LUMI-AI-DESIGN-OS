from __future__ import annotations

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request

from .canvas_document_schemas import (
    CanvasCommandBatchRequest,
    CanvasCommandBatchResponse,
    CanvasDocumentProjectionResponse,
)
from .errors import ApiProblem


class CanvasDocumentService(Protocol):
    async def get_document_head(
        self,
        *,
        organization_id: UUID,
        design_document_id: UUID,
    ) -> CanvasDocumentProjectionResponse: ...

    async def get_artifact_version_document(
        self,
        *,
        organization_id: UUID,
        artifact_version_id: UUID,
    ) -> CanvasDocumentProjectionResponse: ...

    async def apply_commands(
        self,
        *,
        organization_id: UUID,
        design_document_id: UUID,
        request: CanvasCommandBatchRequest,
        actor_id: str,
    ) -> CanvasCommandBatchResponse: ...


def get_canvas_document_service(request: Request) -> CanvasDocumentService:
    service = getattr(request.app.state, "canvas_document_service", None)
    if service is None:
        raise ApiProblem(
            status=503,
            code="canvas_document_service_not_composed",
            title="Canvas document service unavailable",
            detail="The DesignDocument projection/command service is not composed in this deployment.",
        )
    return service


CanvasDocumentServiceDependency = Annotated[
    CanvasDocumentService,
    Depends(get_canvas_document_service),
]
