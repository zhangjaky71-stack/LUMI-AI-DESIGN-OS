from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from lumi_api.collaboration.contracts import (
    Comment,
    CommentRevision,
    CommentThread,
    CommentThreadBundle,
    PresenceState,
)
from lumi_api.collaboration.postgres_repository import (
    CollaborationConflict,
    CollaborationForbidden,
    CollaborationNotFound,
)

from .collaboration_dependencies import CollaborationServiceDependency
from .collaboration_schemas import (
    CreateCommentRequest,
    CreateCommentThreadRequest,
    EditCommentRequest,
    PresenceHeartbeatRequest,
    ThreadStatusRequest,
)
from .common import ProblemDetail, parse_if_match, version_etag
from .errors import ApiProblem
from .headers import IfMatch, OrganizationId

router = APIRouter(prefix="/api/v1")

_ERROR_RESPONSES = {
    400: {"model": ProblemDetail},
    401: {"model": ProblemDetail},
    403: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
    503: {"model": ProblemDetail},
}


def _actor_id(request: Request) -> str:
    context = getattr(request.state, "lumi_context", None)
    actor_id = getattr(context, "actor_id", None)
    if not actor_id:
        raise ApiProblem(
            status=401,
            code="authenticated_actor_required",
            title="Authenticated actor required",
            detail="Collaboration actions require an authenticated user actor.",
        )
    return str(actor_id)


def _expected_revision(value: str) -> int:
    try:
        return parse_if_match(value)
    except ValueError as exc:
        raise ApiProblem(
            status=400,
            code="invalid_comment_if_match",
            title="Invalid comment If-Match",
            detail=str(exc),
        ) from exc


def _set_comment_version(response: Response, revision: int) -> None:
    response.headers["ETag"] = version_etag(revision)
    response.headers["Cache-Control"] = "private, no-cache"


def _translate(exc: Exception) -> ApiProblem:
    if isinstance(exc, CollaborationNotFound):
        return ApiProblem(
            status=404,
            code=str(exc).lower(),
            title="Collaboration resource not found",
            detail=str(exc),
        )
    if isinstance(exc, CollaborationForbidden):
        return ApiProblem(
            status=403,
            code=str(exc).lower(),
            title="Collaboration action forbidden",
            detail=str(exc),
        )
    if isinstance(exc, CollaborationConflict):
        return ApiProblem(
            status=409,
            code=str(exc).lower(),
            title="Collaboration state conflict",
            detail=str(exc),
        )
    if isinstance(exc, ValueError):
        return ApiProblem(
            status=422,
            code="collaboration_request_invalid",
            title="Invalid collaboration request",
            detail=str(exc),
        )
    raise exc


@router.get(
    "/projects/{project_id}/artifacts/{artifact_id}/comment-threads",
    response_model=tuple[CommentThreadBundle, ...],
    responses=_ERROR_RESPONSES,
    tags=["collaboration"],
)
def list_comment_threads(
    project_id: UUID,
    artifact_id: UUID,
    current_artifact_version_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: CollaborationServiceDependency,
    include_history: Annotated[bool, Query()] = False,
    include_resolved: Annotated[bool, Query()] = True,
) -> tuple[CommentThreadBundle, ...]:
    try:
        return service.list_threads(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            current_artifact_version_id=current_artifact_version_id,
            actor_id=_actor_id(request),
            include_history=include_history,
            include_resolved=include_resolved,
        )
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.post(
    "/projects/{project_id}/artifacts/{artifact_id}/comment-threads",
    response_model=CommentThreadBundle,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["collaboration"],
)
def create_comment_thread(
    project_id: UUID,
    artifact_id: UUID,
    body: CreateCommentThreadRequest,
    request: Request,
    organization_id: OrganizationId,
    service: CollaborationServiceDependency,
) -> CommentThreadBundle:
    try:
        return service.create_thread(
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            artifact_version_id=body.artifact_version_id,
            design_node_id=body.design_node_id,
            x=body.x,
            y=body.y,
            body=body.body,
            mention_user_ids=body.mention_user_ids,
            actor_id=_actor_id(request),
        )
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.post(
    "/comment-threads/{thread_id}/comments",
    response_model=Comment,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    tags=["collaboration"],
)
def add_comment(
    thread_id: UUID,
    body: CreateCommentRequest,
    response: Response,
    request: Request,
    organization_id: OrganizationId,
    service: CollaborationServiceDependency,
) -> Comment:
    try:
        comment = service.add_comment(
            organization_id=organization_id,
            thread_id=thread_id,
            body=body.body,
            mention_user_ids=body.mention_user_ids,
            actor_id=_actor_id(request),
        )
        _set_comment_version(response, comment.revision)
        return comment
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.patch(
    "/comments/{comment_id}",
    response_model=Comment,
    responses=_ERROR_RESPONSES,
    tags=["collaboration"],
)
def edit_comment(
    comment_id: UUID,
    body: EditCommentRequest,
    response: Response,
    request: Request,
    organization_id: OrganizationId,
    if_match: IfMatch,
    service: CollaborationServiceDependency,
) -> Comment:
    try:
        comment = service.edit_comment(
            organization_id=organization_id,
            comment_id=comment_id,
            expected_revision=_expected_revision(if_match),
            body=body.body,
            mention_user_ids=body.mention_user_ids,
            actor_id=_actor_id(request),
        )
        _set_comment_version(response, comment.revision)
        return comment
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.delete(
    "/comments/{comment_id}",
    response_model=Comment,
    responses=_ERROR_RESPONSES,
    tags=["collaboration"],
)
def delete_comment(
    comment_id: UUID,
    response: Response,
    request: Request,
    organization_id: OrganizationId,
    if_match: IfMatch,
    service: CollaborationServiceDependency,
) -> Comment:
    try:
        comment = service.delete_comment(
            organization_id=organization_id,
            comment_id=comment_id,
            expected_revision=_expected_revision(if_match),
            actor_id=_actor_id(request),
        )
        _set_comment_version(response, comment.revision)
        return comment
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.patch(
    "/comment-threads/{thread_id}/status",
    response_model=CommentThread,
    responses=_ERROR_RESPONSES,
    tags=["collaboration"],
)
def update_thread_status(
    thread_id: UUID,
    body: ThreadStatusRequest,
    request: Request,
    organization_id: OrganizationId,
    service: CollaborationServiceDependency,
) -> CommentThread:
    try:
        return service.set_thread_status(
            organization_id=organization_id,
            thread_id=thread_id,
            status=body.status,
            actor_id=_actor_id(request),
        )
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.get(
    "/comments/{comment_id}/revisions",
    response_model=tuple[CommentRevision, ...],
    responses=_ERROR_RESPONSES,
    tags=["collaboration"],
)
def list_comment_revisions(
    comment_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: CollaborationServiceDependency,
) -> tuple[CommentRevision, ...]:
    try:
        return service.list_revisions(
            organization_id=organization_id,
            comment_id=comment_id,
            actor_id=_actor_id(request),
        )
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.post(
    "/projects/{project_id}/presence/heartbeat",
    response_model=PresenceState,
    responses=_ERROR_RESPONSES,
    tags=["collaboration-presence"],
)
def heartbeat_presence(
    project_id: UUID,
    body: PresenceHeartbeatRequest,
    request: Request,
    organization_id: OrganizationId,
    service: CollaborationServiceDependency,
) -> PresenceState:
    try:
        return service.heartbeat_presence(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=_actor_id(request),
            display_name=body.display_name,
            avatar_url=body.avatar_url,
            color=body.color,
            artifact_version_id=body.artifact_version_id,
            current_frame_id=body.current_frame_id,
            cursor_x=body.cursor_x,
            cursor_y=body.cursor_y,
            selection_node_ids=body.selection_node_ids,
        )
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.get(
    "/projects/{project_id}/presence",
    response_model=tuple[PresenceState, ...],
    responses=_ERROR_RESPONSES,
    tags=["collaboration-presence"],
)
def list_presence(
    project_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: CollaborationServiceDependency,
) -> tuple[PresenceState, ...]:
    try:
        return service.list_presence(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=_actor_id(request),
        )
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.delete(
    "/projects/{project_id}/presence",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERROR_RESPONSES,
    tags=["collaboration-presence"],
)
def leave_presence(
    project_id: UUID,
    request: Request,
    organization_id: OrganizationId,
    service: CollaborationServiceDependency,
) -> Response:
    try:
        service.leave_presence(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=_actor_id(request),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (CollaborationNotFound, CollaborationForbidden, CollaborationConflict, ValueError) as exc:
        raise _translate(exc) from exc
