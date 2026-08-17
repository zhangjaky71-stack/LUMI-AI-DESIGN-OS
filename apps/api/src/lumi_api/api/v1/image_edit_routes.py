from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from lumi_image_edit import ImageEditPipelineError

from .common import ProblemDetail
from .errors import ApiProblem
from .headers import OrganizationId
from .image_edit_dependencies import ImageEditServiceDependency
from .image_edit_schemas import ImageEditResponse, SubmitImageEditRequest

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


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, LookupError):
        return ApiProblem(
            status=404,
            code="image_edit_not_found",
            title="Image edit not found",
            detail=str(exc),
        )
    if isinstance(exc, PermissionError):
        return ApiProblem(
            status=403,
            code="image_edit_denied",
            title="Image edit denied",
            detail=str(exc),
        )
    if isinstance(exc, ImageEditPipelineError) and "CONFLICT" in str(exc):
        return ApiProblem(
            status=409,
            code="image_edit_conflict",
            title="Image edit conflict",
            detail=str(exc),
        )
    if isinstance(exc, (ImageEditPipelineError, ValueError)):
        return ApiProblem(
            status=422,
            code="image_edit_invalid_request",
            title="Image edit request invalid",
            detail=str(exc),
        )
    raise exc


@router.post(
    "/projects/{project_id}/image-edits",
    response_model=ImageEditResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_RESPONSES,
    tags=["image-edit"],
)
async def submit_image_edit(
    project_id: UUID,
    body: SubmitImageEditRequest,
    organization_id: OrganizationId,
    service: ImageEditServiceDependency,
) -> ImageEditResponse:
    try:
        spec = body.to_domain(
            organization_id=organization_id,
            project_id=project_id,
            code_git_sha=service.code_git_sha,
        )
        return ImageEditResponse.from_job(await service.submit(spec))
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/image-edits/{edit_id}",
    response_model=ImageEditResponse,
    responses=_RESPONSES,
    tags=["image-edit"],
)
def get_image_edit(
    edit_id: str,
    organization_id: OrganizationId,
    service: ImageEditServiceDependency,
) -> ImageEditResponse:
    try:
        return ImageEditResponse.from_job(
            service.get(
                organization_id=str(organization_id),
                edit_id=edit_id,
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/image-edits/{edit_id}/cancel",
    response_model=ImageEditResponse,
    responses=_RESPONSES,
    tags=["image-edit"],
)
async def cancel_image_edit(
    edit_id: str,
    organization_id: OrganizationId,
    service: ImageEditServiceDependency,
) -> ImageEditResponse:
    try:
        return ImageEditResponse.from_job(
            await service.cancel(
                organization_id=str(organization_id),
                edit_id=edit_id,
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/image-edits/{edit_id}/mask-approval",
    response_model=ImageEditResponse,
    responses=_RESPONSES,
    tags=["image-edit"],
)
async def approve_image_edit_mask(
    edit_id: str,
    request: Request,
    organization_id: OrganizationId,
    service: ImageEditServiceDependency,
) -> ImageEditResponse:
    try:
        actor = str(request.state.lumi_context.actor_id)
        return ImageEditResponse.from_job(
            await service.approve_mask(
                organization_id=str(organization_id),
                edit_id=edit_id,
                approved_by=actor,
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/image-edits/{edit_id}/confirm-broad-change",
    response_model=ImageEditResponse,
    responses=_RESPONSES,
    tags=["image-edit"],
)
async def confirm_image_edit_broad_change(
    edit_id: str,
    request: Request,
    organization_id: OrganizationId,
    service: ImageEditServiceDependency,
) -> ImageEditResponse:
    try:
        actor = str(request.state.lumi_context.actor_id)
        return ImageEditResponse.from_job(
            await service.confirm_broad_change(
                organization_id=str(organization_id),
                edit_id=edit_id,
                confirmed_by=actor,
            )
        )
    except Exception as exc:
        raise _translate(exc) from exc
