from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

ActorType = Literal["USER", "AGENT"]
ThreadStatus = Literal["OPEN", "RESOLVED", "REOPENED"]


class CollaborationError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class CollaborationActor:
    actor_id: str
    organization_id: str
    display_name: str
    actor_type: ActorType = "USER"
    agent_run_id: str | None = None

    def __post_init__(self) -> None:
        if self.actor_type == "AGENT" and not self.agent_run_id:
            raise CollaborationError("COLLABORATION_AGENT_RUN_REQUIRED")
        if self.actor_type == "USER" and self.agent_run_id:
            raise CollaborationError("COLLABORATION_USER_AGENT_RUN_FORBIDDEN")


@dataclass(frozen=True, slots=True)
class PresenceState:
    organization_id: str
    project_id: str
    document_id: str
    actor: CollaborationActor
    cursor: tuple[float, float] | None = None
    selection_ids: tuple[str, ...] = ()
    active_frame_id: str | None = None
    last_seen: str = ""


@dataclass(frozen=True, slots=True)
class CommentAnchor:
    project_id: str
    artifact_version_id: str
    design_document_version_id: str
    node_id: str | None = None
    frame_id: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None

    def __post_init__(self) -> None:
        _require_exact_version(self.artifact_version_id, "ARTIFACT_VERSION")
        _require_exact_version(self.design_document_version_id, "DESIGN_VERSION")


@dataclass(frozen=True, slots=True)
class CommentMessage:
    comment_id: str
    actor: CollaborationActor
    body: str
    mention_actor_ids: tuple[str, ...]
    created_at: str
    edited_at: str | None = None
    deleted_at: str | None = None


@dataclass(frozen=True, slots=True)
class CommentThread:
    thread_id: str
    organization_id: str
    anchor: CommentAnchor
    status: ThreadStatus
    messages: tuple[CommentMessage, ...]
    created_at: str
    resolved_at: str | None = None


@dataclass(frozen=True, slots=True)
class CollaborationOperation:
    operation_id: str
    node_id: str
    property_name: str
    value: Any

    @property
    def conflict_key(self) -> tuple[str, str]:
        return (self.node_id, self.property_name)


@dataclass(frozen=True, slots=True)
class CommittedDesignOperation:
    operation: CollaborationOperation
    actor: CollaborationActor
    base_version_id: str
    result_version_id: str
    sequence: int
    committed_at: str


@dataclass(frozen=True, slots=True)
class OperationConflict:
    local_operation: CollaborationOperation
    remote_operation_id: str
    remote_actor_id: str
    remote_actor_type: ActorType
    remote_result_version_id: str
    node_id: str
    property_name: str


@dataclass(frozen=True, slots=True)
class OperationSubmitResult:
    base_version_id: str
    canonical_version_before: str
    canonical_version_after: str
    accepted_operation_ids: tuple[str, ...]
    conflicts: tuple[OperationConflict, ...]
    rebased: bool


@dataclass(frozen=True, slots=True)
class CollaborationAuditEvent:
    event_id: str
    organization_id: str
    project_id: str
    event_type: str
    actor_id: str
    actor_type: ActorType
    agent_run_id: str | None
    target_id: str
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class CollaborationNotification:
    notification_id: str
    organization_id: str
    project_id: str
    recipient_actor_id: str
    kind: str
    thread_id: str
    safe_summary: str
    created_at: str


class CollaborationAuthorizationPort(Protocol):
    def can_view(self, actor: CollaborationActor, project_id: str) -> bool: ...

    def can_comment(self, actor: CollaborationActor, project_id: str) -> bool: ...

    def can_edit(self, actor: CollaborationActor, project_id: str) -> bool: ...

    def can_mention(
        self, actor: CollaborationActor, target_actor_id: str, project_id: str
    ) -> bool: ...


class CollaborationRepository(Protocol):
    def list_threads(self, organization_id: str, project_id: str) -> tuple[CommentThread, ...]: ...

    def get_thread(
        self, organization_id: str, project_id: str, thread_id: str
    ) -> CommentThread | None: ...

    def save_thread(self, thread: CommentThread) -> None: ...


class PresenceStore(Protocol):
    def upsert(self, presence: PresenceState) -> None: ...

    def list(
        self, organization_id: str, project_id: str, document_id: str
    ) -> tuple[PresenceState, ...]: ...

    def remove(
        self, organization_id: str, project_id: str, document_id: str, actor_id: str
    ) -> None: ...


class CanonicalDesignPort(Protocol):
    def current_version(self, project_id: str, document_id: str) -> str: ...

    def operations_since(
        self, project_id: str, document_id: str, version_id: str
    ) -> tuple[CommittedDesignOperation, ...]: ...

    def commit(
        self,
        project_id: str,
        document_id: str,
        expected_version_id: str,
        actor: CollaborationActor,
        operations: tuple[CollaborationOperation, ...],
    ) -> str: ...


class ConstraintValidationPort(Protocol):
    def validate(
        self,
        project_id: str,
        document_id: str,
        canonical_version_id: str,
        operations: tuple[CollaborationOperation, ...],
    ) -> None: ...


class CollaborationAuditPort(Protocol):
    def record(self, event: CollaborationAuditEvent) -> None: ...


class CollaborationNotificationPort(Protocol):
    def send(self, notification: CollaborationNotification) -> None: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_exact_version(value: str, label: str) -> None:
    if not value.strip() or value.strip().lower() in {"latest", "head", "current"}:
        raise CollaborationError(f"COLLABORATION_{label}_MUST_BE_EXACT")


def _clean_body(body: str) -> str:
    normalized = body.strip()
    if not normalized:
        raise CollaborationError("COLLABORATION_COMMENT_EMPTY")
    if len(normalized) > 4000:
        raise CollaborationError("COLLABORATION_COMMENT_TOO_LONG")
    return normalized


class CollaborationEngine:
    def __init__(
        self,
        *,
        authorization: CollaborationAuthorizationPort,
        repository: CollaborationRepository,
        presence: PresenceStore,
        canonical_design: CanonicalDesignPort,
        constraints: ConstraintValidationPort,
        audit: CollaborationAuditPort,
        notifications: CollaborationNotificationPort,
    ) -> None:
        self._authorization = authorization
        self._repository = repository
        self._presence = presence
        self._canonical = canonical_design
        self._constraints = constraints
        self._audit = audit
        self._notifications = notifications

    def workspace(
        self, actor: CollaborationActor, project_id: str, document_id: str
    ) -> dict[str, Any]:
        self._require(actor, project_id, "view")
        return {
            "organization_id": actor.organization_id,
            "project_id": project_id,
            "document_id": document_id,
            "canonical_version_id": self._canonical.current_version(project_id, document_id),
            "presence": self.list_presence(actor, project_id, document_id),
            "threads": self._repository.list_threads(actor.organization_id, project_id),
        }

    def update_presence(
        self,
        actor: CollaborationActor,
        project_id: str,
        document_id: str,
        *,
        cursor: tuple[float, float] | None = None,
        selection_ids: tuple[str, ...] = (),
        active_frame_id: str | None = None,
    ) -> PresenceState:
        self._require(actor, project_id, "view")
        state = PresenceState(
            organization_id=actor.organization_id,
            project_id=project_id,
            document_id=document_id,
            actor=actor,
            cursor=cursor,
            selection_ids=selection_ids[:100],
            active_frame_id=active_frame_id,
            last_seen=_now(),
        )
        self._presence.upsert(state)
        return state

    def list_presence(
        self, actor: CollaborationActor, project_id: str, document_id: str
    ) -> tuple[PresenceState, ...]:
        self._require(actor, project_id, "view")
        return self._presence.list(actor.organization_id, project_id, document_id)

    def leave_presence(
        self, actor: CollaborationActor, project_id: str, document_id: str
    ) -> None:
        self._require(actor, project_id, "view")
        self._presence.remove(actor.organization_id, project_id, document_id, actor.actor_id)

    def create_thread(
        self,
        actor: CollaborationActor,
        anchor: CommentAnchor,
        body: str,
        mention_actor_ids: tuple[str, ...] = (),
    ) -> CommentThread:
        self._require(actor, anchor.project_id, "comment")
        mentions = self._validate_mentions(actor, anchor.project_id, mention_actor_ids)
        timestamp = _now()
        message = CommentMessage(
            comment_id=str(uuid4()),
            actor=actor,
            body=_clean_body(body),
            mention_actor_ids=mentions,
            created_at=timestamp,
        )
        thread = CommentThread(
            thread_id=str(uuid4()),
            organization_id=actor.organization_id,
            anchor=anchor,
            status="OPEN",
            messages=(message,),
            created_at=timestamp,
        )
        self._repository.save_thread(thread)
        self._record(actor, anchor.project_id, "THREAD_CREATED", thread.thread_id, {
            "artifact_version_id": anchor.artifact_version_id,
            "design_document_version_id": anchor.design_document_version_id,
            "node_id": anchor.node_id,
        })
        self._notify_mentions(actor, anchor.project_id, thread.thread_id, mentions)
        return thread

    def reply(
        self,
        actor: CollaborationActor,
        project_id: str,
        thread_id: str,
        body: str,
        mention_actor_ids: tuple[str, ...] = (),
    ) -> CommentThread:
        self._require(actor, project_id, "comment")
        thread = self._thread(actor, project_id, thread_id)
        mentions = self._validate_mentions(actor, project_id, mention_actor_ids)
        message = CommentMessage(
            comment_id=str(uuid4()),
            actor=actor,
            body=_clean_body(body),
            mention_actor_ids=mentions,
            created_at=_now(),
        )
        updated = replace(thread, messages=(*thread.messages, message))
        self._repository.save_thread(updated)
        self._record(actor, project_id, "COMMENT_REPLIED", thread_id, {
            "comment_id": message.comment_id
        })
        self._notify_mentions(actor, project_id, thread_id, mentions)
        for recipient in {item.actor.actor_id for item in thread.messages} - {actor.actor_id}:
            self._notifications.send(CollaborationNotification(
                notification_id=str(uuid4()),
                organization_id=actor.organization_id,
                project_id=project_id,
                recipient_actor_id=recipient,
                kind="COMMENT_REPLY",
                thread_id=thread_id,
                safe_summary=f"{actor.display_name} replied to a review thread.",
                created_at=_now(),
            ))
        return updated

    def set_thread_status(
        self,
        actor: CollaborationActor,
        project_id: str,
        thread_id: str,
        status: Literal["RESOLVED", "REOPENED"],
    ) -> CommentThread:
        self._require(actor, project_id, "comment")
        thread = self._thread(actor, project_id, thread_id)
        updated = replace(
            thread,
            status=status,
            resolved_at=_now() if status == "RESOLVED" else None,
        )
        self._repository.save_thread(updated)
        self._record(actor, project_id, f"THREAD_{status}", thread_id, {})
        return updated

    def edit_comment(
        self,
        actor: CollaborationActor,
        project_id: str,
        thread_id: str,
        comment_id: str,
        body: str,
    ) -> CommentThread:
        self._require(actor, project_id, "comment")
        thread = self._thread(actor, project_id, thread_id)
        found = False
        messages: list[CommentMessage] = []
        for message in thread.messages:
            if message.comment_id != comment_id:
                messages.append(message)
                continue
            if message.actor.actor_id != actor.actor_id:
                raise CollaborationError("COLLABORATION_COMMENT_EDIT_FORBIDDEN", 403)
            if message.deleted_at:
                raise CollaborationError("COLLABORATION_COMMENT_DELETED", 409)
            found = True
            messages.append(replace(message, body=_clean_body(body), edited_at=_now()))
        if not found:
            raise CollaborationError("COLLABORATION_COMMENT_NOT_FOUND", 404)
        updated = replace(thread, messages=tuple(messages))
        self._repository.save_thread(updated)
        self._record(actor, project_id, "COMMENT_EDITED", comment_id, {})
        return updated

    def delete_comment(
        self,
        actor: CollaborationActor,
        project_id: str,
        thread_id: str,
        comment_id: str,
    ) -> CommentThread:
        self._require(actor, project_id, "comment")
        thread = self._thread(actor, project_id, thread_id)
        found = False
        messages: list[CommentMessage] = []
        for message in thread.messages:
            if message.comment_id != comment_id:
                messages.append(message)
                continue
            if message.actor.actor_id != actor.actor_id:
                raise CollaborationError("COLLABORATION_COMMENT_DELETE_FORBIDDEN", 403)
            found = True
            messages.append(replace(message, body="", deleted_at=_now()))
        if not found:
            raise CollaborationError("COLLABORATION_COMMENT_NOT_FOUND", 404)
        updated = replace(thread, messages=tuple(messages))
        self._repository.save_thread(updated)
        self._record(actor, project_id, "COMMENT_DELETED", comment_id, {"tombstoned": True})
        return updated

    def submit_operations(
        self,
        actor: CollaborationActor,
        project_id: str,
        document_id: str,
        base_version_id: str,
        operations: tuple[CollaborationOperation, ...],
    ) -> OperationSubmitResult:
        self._require(actor, project_id, "edit")
        _require_exact_version(base_version_id, "BASE_DESIGN_VERSION")
        if not operations:
            raise CollaborationError("COLLABORATION_OPERATIONS_REQUIRED")
        if len({op.operation_id for op in operations}) != len(operations):
            raise CollaborationError("COLLABORATION_OPERATION_ID_DUPLICATE")

        current = self._canonical.current_version(project_id, document_id)
        remote = () if base_version_id == current else self._canonical.operations_since(
            project_id, document_id, base_version_id
        )
        remote_by_key = {item.operation.conflict_key: item for item in remote}
        accepted: list[CollaborationOperation] = []
        conflicts: list[OperationConflict] = []
        for operation in operations:
            competing = remote_by_key.get(operation.conflict_key)
            if competing is None:
                accepted.append(operation)
                continue
            conflicts.append(OperationConflict(
                local_operation=operation,
                remote_operation_id=competing.operation.operation_id,
                remote_actor_id=competing.actor.actor_id,
                remote_actor_type=competing.actor.actor_type,
                remote_result_version_id=competing.result_version_id,
                node_id=operation.node_id,
                property_name=operation.property_name,
            ))

        result_version = current
        if accepted:
            accepted_tuple = tuple(accepted)
            self._constraints.validate(
                project_id, document_id, current, accepted_tuple
            )
            result_version = self._canonical.commit(
                project_id, document_id, current, actor, accepted_tuple
            )
            for operation in accepted:
                self._record(actor, project_id, "DESIGN_OPERATION_COMMITTED", operation.operation_id, {
                    "document_id": document_id,
                    "base_version_id": base_version_id,
                    "result_version_id": result_version,
                    "node_id": operation.node_id,
                    "property_name": operation.property_name,
                })
        for conflict in conflicts:
            self._record(actor, project_id, "DESIGN_OPERATION_CONFLICT", conflict.local_operation.operation_id, {
                "document_id": document_id,
                "node_id": conflict.node_id,
                "property_name": conflict.property_name,
                "remote_operation_id": conflict.remote_operation_id,
                "local_edit_preserved": True,
            })
        return OperationSubmitResult(
            base_version_id=base_version_id,
            canonical_version_before=current,
            canonical_version_after=result_version,
            accepted_operation_ids=tuple(item.operation_id for item in accepted),
            conflicts=tuple(conflicts),
            rebased=base_version_id != current,
        )

    def reconnect(
        self,
        actor: CollaborationActor,
        project_id: str,
        document_id: str,
        base_version_id: str,
        buffered_operations: tuple[CollaborationOperation, ...],
    ) -> OperationSubmitResult:
        return self.submit_operations(
            actor, project_id, document_id, base_version_id, buffered_operations
        )

    def _thread(
        self, actor: CollaborationActor, project_id: str, thread_id: str
    ) -> CommentThread:
        thread = self._repository.get_thread(actor.organization_id, project_id, thread_id)
        if thread is None:
            raise CollaborationError("COLLABORATION_THREAD_NOT_FOUND", 404)
        return thread

    def _validate_mentions(
        self,
        actor: CollaborationActor,
        project_id: str,
        mention_actor_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        mentions = tuple(dict.fromkeys(mention_actor_ids))
        for target in mentions:
            if target == actor.actor_id:
                continue
            if not self._authorization.can_mention(actor, target, project_id):
                raise CollaborationError("COLLABORATION_MENTION_FORBIDDEN", 403)
        return mentions

    def _notify_mentions(
        self,
        actor: CollaborationActor,
        project_id: str,
        thread_id: str,
        mentions: tuple[str, ...],
    ) -> None:
        for recipient in mentions:
            if recipient == actor.actor_id:
                continue
            self._notifications.send(CollaborationNotification(
                notification_id=str(uuid4()),
                organization_id=actor.organization_id,
                project_id=project_id,
                recipient_actor_id=recipient,
                kind="MENTION",
                thread_id=thread_id,
                safe_summary=f"{actor.display_name} mentioned you in a review thread.",
                created_at=_now(),
            ))

    def _require(
        self, actor: CollaborationActor, project_id: str, action: Literal["view", "comment", "edit"]
    ) -> None:
        allowed = {
            "view": self._authorization.can_view,
            "comment": self._authorization.can_comment,
            "edit": self._authorization.can_edit,
        }[action](actor, project_id)
        if not allowed:
            raise CollaborationError("COLLABORATION_FORBIDDEN", 403)

    def _record(
        self,
        actor: CollaborationActor,
        project_id: str,
        event_type: str,
        target_id: str,
        metadata: dict[str, Any],
    ) -> None:
        self._audit.record(CollaborationAuditEvent(
            event_id=str(uuid4()),
            organization_id=actor.organization_id,
            project_id=project_id,
            event_type=event_type,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            agent_run_id=actor.agent_run_id,
            target_id=target_id,
            metadata=metadata,
            created_at=_now(),
        ))


class InMemoryCollaborationRepository:
    def __init__(self) -> None:
        self.threads: dict[tuple[str, str, str], CommentThread] = {}

    def list_threads(self, organization_id: str, project_id: str) -> tuple[CommentThread, ...]:
        values = [
            item for (org, project, _), item in self.threads.items()
            if org == organization_id and project == project_id
        ]
        return tuple(sorted(values, key=lambda item: item.created_at, reverse=True))

    def get_thread(
        self, organization_id: str, project_id: str, thread_id: str
    ) -> CommentThread | None:
        return self.threads.get((organization_id, project_id, thread_id))

    def save_thread(self, thread: CommentThread) -> None:
        self.threads[(thread.organization_id, thread.anchor.project_id, thread.thread_id)] = thread


class InMemoryPresenceStore:
    """Ephemeral only. Replace with Redis/realtime in multi-instance production."""

    def __init__(self) -> None:
        self.states: dict[tuple[str, str, str, str], PresenceState] = {}

    def upsert(self, presence: PresenceState) -> None:
        self.states[(
            presence.organization_id,
            presence.project_id,
            presence.document_id,
            presence.actor.actor_id,
        )] = presence

    def list(
        self, organization_id: str, project_id: str, document_id: str
    ) -> tuple[PresenceState, ...]:
        return tuple(
            state for (org, project, document, _), state in self.states.items()
            if org == organization_id and project == project_id and document == document_id
        )

    def remove(
        self, organization_id: str, project_id: str, document_id: str, actor_id: str
    ) -> None:
        self.states.pop((organization_id, project_id, document_id, actor_id), None)


class StaticCollaborationAuthorization:
    VIEW = "VIEW"
    COMMENT = "COMMENT"
    EDIT = "EDIT"

    def __init__(
        self,
        permissions: dict[str, dict[str, frozenset[str]]],
        actor_organizations: dict[str, str],
    ) -> None:
        self.permissions = permissions
        self.actor_organizations = actor_organizations

    def _has(self, actor: CollaborationActor, project_id: str, permission: str) -> bool:
        if self.actor_organizations.get(actor.actor_id) != actor.organization_id:
            return False
        return permission in self.permissions.get(actor.actor_id, {}).get(project_id, frozenset())

    def can_view(self, actor: CollaborationActor, project_id: str) -> bool:
        return self._has(actor, project_id, self.VIEW)

    def can_comment(self, actor: CollaborationActor, project_id: str) -> bool:
        return self._has(actor, project_id, self.COMMENT)

    def can_edit(self, actor: CollaborationActor, project_id: str) -> bool:
        return self._has(actor, project_id, self.EDIT)

    def can_mention(
        self, actor: CollaborationActor, target_actor_id: str, project_id: str
    ) -> bool:
        return self.can_comment(actor, project_id) and (
            self.actor_organizations.get(target_actor_id) == actor.organization_id
            and self.VIEW in self.permissions.get(target_actor_id, {}).get(project_id, frozenset())
        )


class InMemoryCanonicalDesign:
    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], list[str]] = {}
        self._commits: dict[tuple[str, str], list[CommittedDesignOperation]] = {}
        self._sequence = 0

    def seed(self, project_id: str, document_id: str, version_id: str) -> None:
        _require_exact_version(version_id, "DESIGN_VERSION")
        self._versions[(project_id, document_id)] = [version_id]
        self._commits[(project_id, document_id)] = []

    def current_version(self, project_id: str, document_id: str) -> str:
        versions = self._versions.get((project_id, document_id))
        if not versions:
            raise CollaborationError("COLLABORATION_DOCUMENT_NOT_FOUND", 404)
        return versions[-1]

    def operations_since(
        self, project_id: str, document_id: str, version_id: str
    ) -> tuple[CommittedDesignOperation, ...]:
        key = (project_id, document_id)
        versions = self._versions.get(key, [])
        if version_id not in versions:
            raise CollaborationError("COLLABORATION_BASE_VERSION_NOT_FOUND", 409)
        index = versions.index(version_id)
        allowed_result_versions = set(versions[index + 1 :])
        return tuple(
            item for item in self._commits.get(key, [])
            if item.result_version_id in allowed_result_versions
        )

    def commit(
        self,
        project_id: str,
        document_id: str,
        expected_version_id: str,
        actor: CollaborationActor,
        operations: tuple[CollaborationOperation, ...],
    ) -> str:
        current = self.current_version(project_id, document_id)
        if current != expected_version_id:
            raise CollaborationError("COLLABORATION_CANONICAL_HEAD_CONFLICT", 409)
        versions = self._versions[(project_id, document_id)]
        result = self._next_version(current, len(versions) + 1)
        versions.append(result)
        for operation in operations:
            self._sequence += 1
            self._commits[(project_id, document_id)].append(CommittedDesignOperation(
                operation=operation,
                actor=actor,
                base_version_id=current,
                result_version_id=result,
                sequence=self._sequence,
                committed_at=_now(),
            ))
        return result

    @staticmethod
    def _next_version(current: str, fallback: int) -> str:
        prefix, marker, suffix = current.rpartition("v")
        if marker and suffix.isdigit():
            return f"{prefix}v{int(suffix) + 1}"
        return f"{current}-collab-{fallback}"


class RecordingConstraintValidator:
    def __init__(self, forbidden_properties: frozenset[str] = frozenset()) -> None:
        self.forbidden_properties = forbidden_properties
        self.calls: list[tuple[str, str, str, tuple[CollaborationOperation, ...]]] = []

    def validate(
        self,
        project_id: str,
        document_id: str,
        canonical_version_id: str,
        operations: tuple[CollaborationOperation, ...],
    ) -> None:
        self.calls.append((project_id, document_id, canonical_version_id, operations))
        if any(item.property_name in self.forbidden_properties for item in operations):
            raise CollaborationError("COLLABORATION_HARD_CONSTRAINT_FAILED", 409)


class RecordingCollaborationAudit:
    def __init__(self) -> None:
        self.events: list[CollaborationAuditEvent] = []

    def record(self, event: CollaborationAuditEvent) -> None:
        self.events.append(event)


class RecordingCollaborationNotifications:
    def __init__(self) -> None:
        self.notifications: list[CollaborationNotification] = []

    def send(self, notification: CollaborationNotification) -> None:
        self.notifications.append(notification)
