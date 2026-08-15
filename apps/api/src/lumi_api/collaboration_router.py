from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, Protocol

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from lumi_project_core.collaboration import (
    CollaborationActor,
    CollaborationEngine,
    CollaborationError,
    CollaborationOperation,
    CommentAnchor,
)

HttpContextResolver = Callable[[Request], CollaborationActor | Awaitable[CollaborationActor]]
WsContextResolver = Callable[[WebSocket], CollaborationActor | Awaitable[CollaborationActor]]


@dataclass(frozen=True, slots=True)
class CollaborationWorkspaceMetadata:
    """Trusted Project/Auth projection needed to bootstrap product collaboration."""

    document_id: str
    artifact_version_id: str
    current_user: dict[str, Any]
    members: tuple[dict[str, Any], ...]
    notifications: tuple[dict[str, Any], ...] = ()


WorkspaceMetadataResolver = Callable[
    [CollaborationActor, str],
    CollaborationWorkspaceMetadata | Awaitable[CollaborationWorkspaceMetadata],
]


class RealtimeHubPort(Protocol):
    async def connect(self, room: str, socket: WebSocket) -> None: ...

    async def disconnect(self, room: str, socket: WebSocket) -> None: ...

    async def broadcast(self, room: str, payload: dict[str, Any]) -> None: ...


class InProcessRealtimeHub:
    """Single-process dev/test fanout; production must use a multi-instance realtime adapter."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, room: str, socket: WebSocket) -> None:
        await socket.accept()
        self._rooms.setdefault(room, set()).add(socket)

    async def disconnect(self, room: str, socket: WebSocket) -> None:
        sockets = self._rooms.get(room)
        if not sockets:
            return
        sockets.discard(socket)
        if not sockets:
            self._rooms.pop(room, None)

    async def broadcast(self, room: str, payload: dict[str, Any]) -> None:
        for socket in tuple(self._rooms.get(room, set())):
            try:
                await socket.send_json(payload)
            except RuntimeError:
                self._rooms.get(room, set()).discard(socket)


class AnchorBody(BaseModel):
    artifact_version_id: str
    design_document_version_id: str
    node_id: str | None = None
    frame_id: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    mention_actor_ids: list[str] = Field(default_factory=list, max_length=50)


class CreateThreadBody(CommentBody):
    anchor: AnchorBody


class OperationsBody(BaseModel):
    base_version_id: str
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=200)


async def _resolve[T](value: T | Awaitable[T]) -> T:
    if inspect.isawaitable(value):
        return await value
    return value


def _operation(value: dict[str, Any]) -> CollaborationOperation:
    operation_id = str(value.get("operation_id", "")).strip()
    node_id = str(value.get("node_id", "")).strip()
    property_name = str(value.get("property_name", "")).strip()
    if not operation_id or not node_id or not property_name:
        raise CollaborationError("COLLABORATION_OPERATION_INVALID")
    return CollaborationOperation(
        operation_id=operation_id,
        node_id=node_id,
        property_name=property_name,
        value=value.get("value"),
    )


def _room(organization_id: str, project_id: str, document_id: str) -> str:
    return f"{organization_id}:{project_id}:{document_id}"


def _safe_member_index(metadata: CollaborationWorkspaceMetadata) -> dict[str, dict[str, Any]]:
    members: dict[str, dict[str, Any]] = {}
    for member in metadata.members:
        actor_id = str(member.get("actor_id", ""))
        if actor_id:
            members[actor_id] = dict(member)
    current_id = str(metadata.current_user.get("actor_id", ""))
    if current_id:
        members[current_id] = dict(metadata.current_user)
    return members


def _product_workspace(
    base: dict[str, Any],
    metadata: CollaborationWorkspaceMetadata,
) -> dict[str, Any]:
    canonical = str(base["canonical_version_id"])
    member_index = _safe_member_index(metadata)
    presence = list(base.get("presence", []))
    for item in presence:
        actor = item.get("actor", {})
        actor_id = str(actor.get("actor_id", ""))
        if actor_id in member_index:
            item["actor"] = member_index[actor_id]
    threads = list(base.get("threads", []))
    for thread in threads:
        anchor = thread.get("anchor", {})
        anchor["historical"] = anchor.get("design_document_version_id") != canonical
        for message in thread.get("messages", []):
            actor = message.get("actor", {})
            actor_id = str(actor.get("actor_id", ""))
            if actor_id in member_index:
                message["actor"] = member_index[actor_id]
    return {
        **base,
        "artifact_version_id": metadata.artifact_version_id,
        "current_user": metadata.current_user,
        "members": list(metadata.members),
        "presence": presence,
        "threads": threads,
        "notifications": list(metadata.notifications),
        "realtime": {
            "transport": "WEBSOCKET",
            "presence_is_ephemeral": True,
            "canonical_write_transport": "HTTP_DESIGN_OPERATION_API",
        },
    }


def create_collaboration_router(
    *,
    engine: CollaborationEngine,
    resolve_http_context: HttpContextResolver,
    resolve_ws_context: WsContextResolver,
    resolve_workspace_metadata: WorkspaceMetadataResolver,
    hub: RealtimeHubPort | None = None,
) -> APIRouter:
    """Create the collaboration transport boundary.

    Resolver callbacks MUST be backed by the trusted NODE-16 session/tenant and Project services.
    This router never accepts auth tokens from request payloads or WebSocket query params. WebSocket is
    awareness only: canonical design mutations are accepted only by the HTTP operation endpoints.
    """

    router = APIRouter(prefix="/api/v1", tags=["collaboration"])
    realtime = hub or InProcessRealtimeHub()

    @router.get("/projects/{project_id}/collaboration")
    async def workspace(project_id: str, request: Request) -> dict[str, Any]:
        actor = await _resolve(resolve_http_context(request))
        metadata = await _resolve(resolve_workspace_metadata(actor, project_id))
        if str(metadata.current_user.get("actor_id", "")) != actor.actor_id:
            raise CollaborationError("COLLABORATION_WORKSPACE_ACTOR_MISMATCH", 403)
        base = _serialize(engine.workspace(actor, project_id, metadata.document_id))
        return _product_workspace(base, metadata)

    @router.post("/projects/{project_id}/collaboration/threads")
    async def create_thread(
        project_id: str, payload: CreateThreadBody, request: Request
    ) -> dict[str, Any]:
        actor = await _resolve(resolve_http_context(request))
        anchor = CommentAnchor(project_id=project_id, **payload.anchor.model_dump())
        return _serialize(
            engine.create_thread(actor, anchor, payload.body, tuple(payload.mention_actor_ids))
        )

    @router.post("/projects/{project_id}/collaboration/threads/{thread_id}/replies")
    async def reply(
        project_id: str, thread_id: str, payload: CommentBody, request: Request
    ) -> dict[str, Any]:
        actor = await _resolve(resolve_http_context(request))
        return _serialize(
            engine.reply(actor, project_id, thread_id, payload.body, tuple(payload.mention_actor_ids))
        )

    @router.post("/projects/{project_id}/collaboration/threads/{thread_id}:resolve")
    async def resolve(project_id: str, thread_id: str, request: Request) -> dict[str, Any]:
        actor = await _resolve(resolve_http_context(request))
        return _serialize(engine.set_thread_status(actor, project_id, thread_id, "RESOLVED"))

    @router.post("/projects/{project_id}/collaboration/threads/{thread_id}:reopen")
    async def reopen(project_id: str, thread_id: str, request: Request) -> dict[str, Any]:
        actor = await _resolve(resolve_http_context(request))
        return _serialize(engine.set_thread_status(actor, project_id, thread_id, "REOPENED"))

    @router.post("/projects/{project_id}/documents/{document_id}/collaboration/operations")
    async def submit_operations(
        project_id: str, document_id: str, payload: OperationsBody, request: Request
    ) -> dict[str, Any]:
        actor = await _resolve(resolve_http_context(request))
        operations = tuple(_operation(item) for item in payload.operations)
        return _serialize(
            engine.submit_operations(
                actor, project_id, document_id, payload.base_version_id, operations
            )
        )

    @router.post("/projects/{project_id}/documents/{document_id}/collaboration/reconnect")
    async def reconnect(
        project_id: str, document_id: str, payload: OperationsBody, request: Request
    ) -> dict[str, Any]:
        actor = await _resolve(resolve_http_context(request))
        operations = tuple(_operation(item) for item in payload.operations)
        return _serialize(
            engine.reconnect(actor, project_id, document_id, payload.base_version_id, operations)
        )

    @router.websocket("/projects/{project_id}/collaboration/ws")
    async def realtime_socket(socket: WebSocket, project_id: str, document_id: str) -> None:
        try:
            actor = await _resolve(resolve_ws_context(socket))
            engine.update_presence(actor, project_id, document_id)
        except CollaborationError:
            await socket.close(code=4403, reason="COLLABORATION_FORBIDDEN")
            return

        room = _room(actor.organization_id, project_id, document_id)
        await realtime.connect(room, socket)
        await realtime.broadcast(
            room,
            {
                "type": "PRESENCE_SNAPSHOT",
                "document_id": document_id,
                "presence": [
                    _serialize(item)
                    for item in engine.list_presence(actor, project_id, document_id)
                ],
            },
        )
        try:
            while True:
                message = await socket.receive_json()
                message_type = str(message.get("type", ""))
                if message_type == "AWARENESS_UPDATE":
                    raw_cursor = message.get("cursor")
                    cursor = None
                    if isinstance(raw_cursor, list) and len(raw_cursor) == 2:
                        cursor = (float(raw_cursor[0]), float(raw_cursor[1]))
                    raw_selection = message.get("selection_ids", [])
                    selection = (
                        tuple(str(item) for item in raw_selection[:100])
                        if isinstance(raw_selection, list)
                        else ()
                    )
                    state = engine.update_presence(
                        actor,
                        project_id,
                        document_id,
                        cursor=cursor,
                        selection_ids=selection,
                        active_frame_id=(
                            str(message.get("active_frame_id"))
                            if message.get("active_frame_id")
                            else None
                        ),
                    )
                    await realtime.broadcast(
                        room,
                        {"type": "AWARENESS_UPDATE", "presence": _serialize(state)},
                    )
                    continue
                if message_type in {"DESIGN_OPERATION", "CRDT_UPDATE", "CANONICAL_WRITE"}:
                    await socket.send_json(
                        {
                            "type": "WRITE_REJECTED",
                            "code": "COLLABORATION_CANONICAL_WRITE_REQUIRES_HTTP_OPERATION_API",
                        }
                    )
                    continue
                await socket.send_json(
                    {
                        "type": "MESSAGE_REJECTED",
                        "code": "COLLABORATION_REALTIME_MESSAGE_UNSUPPORTED",
                    }
                )
        except WebSocketDisconnect:
            pass
        finally:
            engine.leave_presence(actor, project_id, document_id)
            await realtime.disconnect(room, socket)
            await realtime.broadcast(
                room,
                {
                    "type": "PRESENCE_SNAPSHOT",
                    "document_id": document_id,
                    "presence": [
                        _serialize(item)
                        for item in engine.list_presence(actor, project_id, document_id)
                    ],
                },
            )

    return router


def _serialize(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value
