from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

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
    PAUSED = "paused"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
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


E = TypeVar("E", bound=StrEnum)

_PROJECT_TRANSITIONS = {
    ProjectStatus.DRAFT: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED}),
    ProjectStatus.ACTIVE: frozenset({ProjectStatus.PAUSED, ProjectStatus.ARCHIVED}),
    ProjectStatus.PAUSED: frozenset({ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED}),
    ProjectStatus.ARCHIVED: frozenset(),
}

_AGENT_RUN_TRANSITIONS = {
    AgentRunStatus.PENDING: frozenset({AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED}),
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.WAITING_USER,
            AgentRunStatus.PAUSED,
            AgentRunStatus.CANCEL_REQUESTED,
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.FAILED,
        }
    ),
    AgentRunStatus.WAITING_USER: frozenset(
        {AgentRunStatus.RUNNING, AgentRunStatus.CANCEL_REQUESTED}
    ),
    AgentRunStatus.PAUSED: frozenset({AgentRunStatus.RUNNING, AgentRunStatus.CANCEL_REQUESTED}),
    AgentRunStatus.CANCEL_REQUESTED: frozenset({AgentRunStatus.CANCELLED}),
    AgentRunStatus.CANCELLED: frozenset(),
    AgentRunStatus.SUCCEEDED: frozenset(),
    AgentRunStatus.FAILED: frozenset(),
}

_TASK_TRANSITIONS = {
    TaskStatus.PENDING: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.READY: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.WAITING_USER,
            TaskStatus.WAITING_DEPENDENCY,
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_USER: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.WAITING_DEPENDENCY: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED: frozenset({TaskStatus.READY}),
    TaskStatus.CANCELLED: frozenset(),
}

_ARTIFACT_VERSION_TRANSITIONS = {
    ArtifactVersionStatus.DRAFT: frozenset(
        {ArtifactVersionStatus.READY, ArtifactVersionStatus.REJECTED}
    ),
    ArtifactVersionStatus.READY: frozenset(
        {ArtifactVersionStatus.APPROVED, ArtifactVersionStatus.REJECTED}
    ),
    ArtifactVersionStatus.APPROVED: frozenset(),
    ArtifactVersionStatus.REJECTED: frozenset(),
}


def _transition(current: E, target: E, transitions: dict[E, frozenset[E]]) -> E:
    if target not in transitions[current]:
        raise InvalidTransition(f"cannot transition {current.value} -> {target.value}")
    return target


def transition_project(current: ProjectStatus, target: ProjectStatus) -> ProjectStatus:
    return _transition(current, target, _PROJECT_TRANSITIONS)


def transition_agent_run(current: AgentRunStatus, target: AgentRunStatus) -> AgentRunStatus:
    return _transition(current, target, _AGENT_RUN_TRANSITIONS)


def transition_task(current: TaskStatus, target: TaskStatus) -> TaskStatus:
    return _transition(current, target, _TASK_TRANSITIONS)


def transition_artifact_version(
    current: ArtifactVersionStatus, target: ArtifactVersionStatus
) -> ArtifactVersionStatus:
    return _transition(current, target, _ARTIFACT_VERSION_TRANSITIONS)
