from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, status

from lumi_image_generation import GenerationBudgetError, ImageGenerationPipelineError
from lumi_image_generation.repository import OperationSemanticConflict

from .common import ProblemDetail
from .errors import ApiProblem
from .headers import OrganizationId
from .image_generation_dependencies import ImageGenerationServiceDependency
from .image_generation_schemas import ImageGenerationResponse, SubmitImageGenerationRequest

router = APIRouter(prefix="/api/v1")
_RESPONSES = {
    400: {"model": ProblemDetail},
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, LookupError):
        return ApiProblem(
            status=404,
            code="image_generation_not_found",
            title="Image generation not found",
            detail=str(exc),
        )
    if isinstance(exc, PermissionError):
        return ApiProblem(
            status=403,
            code="image_generation_reference_denied",
            title="Image generation reference denied",
            detail=str(exc),
        )
    if isinstance(exc, (OperationSemanticConflict, GenerationBudgetError)):
        return ApiProblem(
            status=409,
            code="image_generation_conflict",
            title="Image generation conflict",
            detail=str(exc),
        )
    if isinstance(exc, (ImageGenerationPipelineError, ValueError)):
        return ApiProblem(
            status=422,
            code="image_generation_invalid_request",
            title="Image generation request invalid",
            detail=str(exc),
        )
    raise exc


@router.post(
    "/projects/{project_id}/image-generations",
    response_model=ImageGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_RESPONSES,
    tags=["image-generation"],
)
async def submit_image_generation(
    project_id: UUID,
    body: SubmitImageGenerationRequest,
    organization_id: OrganizationId,
    service: ImageGenerationServiceDependency,
) -> ImageGenerationResponse:
    try:
        spec = body.to_domain(
            organization_id=organization_id,
            project_id=project_id,
            code_git_sha=service.code_git_sha,
        )
        job = await service.submit(spec, now=_now())
        return ImageGenerationResponse.from_job(job)
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/image-generations/{generation_id}",
    response_model=ImageGenerationResponse,
    responses=_RESPONSES,
    tags=["image-generation"],
)
def get_image_generation(
    generation_id: UUID,
    organization_id: OrganizationId,
    service: ImageGenerationServiceDependency,
) -> ImageGenerationResponse:
    try:
        return ImageGenerationResponse.from_job(
            service.get(organization_id=organization_id, generation_id=generation_id)
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/image-generations/{generation_id}/cancel",
    response_model=ImageGenerationResponse,
    responses=_RESPONSES,
    tags=["image-generation"],
)
async def cancel_image_generation(
    generation_id: UUID,
    organization_id: OrganizationId,
    service: ImageGenerationServiceDependency,
) -> ImageGenerationResponse:
    try:
        job = await service.cancel(
            organization_id=organization_id,
            generation_id=generation_id,
            now=_now(),
        )
        return ImageGenerationResponse.from_job(job)
    except Exception as exc:
        raise _translate(exc) from exc
