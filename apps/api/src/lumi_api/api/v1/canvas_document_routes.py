from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from .canvas_document_dependencies import CanvasDocumentServiceDependency
from .canvas_document_schemas import (
    CanvasCommandBatchRequest,
    CanvasCommandBatchResponse,
    CanvasDocumentProjectionResponse,
)
from .headers import OrganizationId

router = APIRouter(prefix="/api/v1", tags=["canvas-document"])


@router.get(
    "/design-documents/{design_document_id}/canvas",
    response_model=CanvasDocumentProjectionResponse,
)
async def get_canvas_document(
    design_document_id: UUID,
    organization_id: OrganizationId,
    service: CanvasDocumentServiceDependency,
) -> CanvasDocumentProjectionResponse:
    return await service.get_document_head(
        organization_id=organization_id,
        design_document_id=design_document_id,
    )


@router.get(
    "/artifact-versions/{artifact_version_id}/canvas",
    response_model=CanvasDocumentProjectionResponse,
)
async def get_artifact_version_canvas(
    artifact_version_id: UUID,
    organization_id: OrganizationId,
    service: CanvasDocumentServiceDependency,
) -> CanvasDocumentProjectionResponse:
    return await service.get_artifact_version_document(
        organization_id=organization_id,
        artifact_version_id=artifact_version_id,
    )


@router.post(
    "/design-documents/{design_document_id}/commands",
    response_model=CanvasCommandBatchResponse,
)
async def apply_canvas_commands(
    design_document_id: UUID,
    body: CanvasCommandBatchRequest,
    request: Request,
    organization_id: OrganizationId,
    service: CanvasDocumentServiceDependency,
) -> CanvasCommandBatchResponse:
    context = getattr(request.state, "lumi_context", None)
    actor_id = getattr(context, "actor_id", None)
    if not isinstance(actor_id, str) or not actor_id:
        # Auth guard should always establish this before the route executes.
        from .errors import ApiProblem

        raise ApiProblem(
            status=503,
            code="canvas_actor_context_missing",
            title="Canvas actor unavailable",
            detail="Authenticated request context is missing its actor identity.",
        )
    return await service.apply_commands(
        organization_id=organization_id,
        design_document_id=design_document_id,
        request=body,
        actor_id=actor_id,
    )
