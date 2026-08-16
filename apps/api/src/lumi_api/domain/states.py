from __future__ import annotations

from enum import StrEnum

from .errors import InvalidTransition


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_DEPENDENCY = "waiting_dependency"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactVersionStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"


class GenerationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


PROJECT_TRANSITIONS: dict[ProjectStatus, frozenset[ProjectStatus]] = {
    ProjectStatus.DRAFT: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED}),
    ProjectStatus.ACTIVE: frozenset({ProjectStatus.PAUSED, ProjectStatus.ARCHIVED}),
    ProjectStatus.PAUSED: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED}),
    ProjectStatus.ARCHIVED: frozenset({ProjectStatus.ACTIVE}),
}

AGENT_RUN_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.PENDING: frozenset({AgentRunStatus.RUNNING}),
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.WAITING_USER,
            AgentRunStatus.CANCEL_REQUESTED,
            AgentRunStatus.PAUSED,
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.FAILED,
        }
    ),
    AgentRunStatus.WAITING_USER: frozenset(
        {AgentRunStatus.RUNNING, AgentRunStatus.CANCEL_REQUESTED}
    ),
    AgentRunStatus.CANCEL_REQUESTED: frozenset({AgentRunStatus.CANCELLED}),
    AgentRunStatus.PAUSED: frozenset({AgentRunStatus.RUNNING, AgentRunStatus.CANCEL_REQUESTED}),
    AgentRunStatus.CANCELLED: frozenset(),
    AgentRunStatus.SUCCEEDED: frozenset(),
    AgentRunStatus.FAILED: frozenset(),
}

TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.READY: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.SUCCEEDED,
            TaskStatus.WAITING_USER,
            TaskStatus.WAITING_DEPENDENCY,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_USER: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.WAITING_DEPENDENCY: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

ARTIFACT_VERSION_TRANSITIONS: dict[
    ArtifactVersionStatus, frozenset[ArtifactVersionStatus]
] = {
    ArtifactVersionStatus.DRAFT: frozenset(
        {ArtifactVersionStatus.READY, ArtifactVersionStatus.REJECTED}
    ),
    ArtifactVersionStatus.READY: frozenset(
        {ArtifactVersionStatus.APPROVED, ArtifactVersionStatus.REJECTED}
    ),
    ArtifactVersionStatus.APPROVED: frozenset(),
    ArtifactVersionStatus.REJECTED: frozenset(),
}

GENERATION_TRANSITIONS: dict[GenerationStatus, frozenset[GenerationStatus]] = {
    GenerationStatus.PENDING: frozenset({GenerationStatus.RUNNING, GenerationStatus.CANCELLED}),
    GenerationStatus.RUNNING: frozenset(
        {GenerationStatus.COMPLETED, GenerationStatus.FAILED, GenerationStatus.CANCELLED}
    ),
    GenerationStatus.COMPLETED: frozenset(),
    GenerationStatus.FAILED: frozenset(),
    GenerationStatus.CANCELLED: frozenset(),
}


def require_transition[S: StrEnum](
    current: S,
    target: S,
    transitions: dict[S, frozenset[S]],
) -> S:
    if target not in transitions[current]:
        raise InvalidTransition(f"invalid transition: {current.value} -> {target.value}")
    return target
