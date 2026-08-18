from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

SafeAgentEventType = Literal[
    "run.started",
    "node.started",
    "agent.status",
    "agent.delta",
    "tool.call",
    "task.progress",
    "approval.required",
    "artifact.created",
    "run.completed",
    "run.cancelled",
    "run.waiting_external",
]

_FORBIDDEN_PUBLIC_KEYS = {
    "prompt",
    "messages",
    "reasoning",
    "chain_of_thought",
    "scratchpad",
    "raw_response",
    "tool_output",
    "secret",
    "password",
    "credential",
    "credentials",
    "api_key",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "cookies",
    "headers",
}
_FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "access_token",
    "refresh_token",
    "authorization",
    "credential",
    "password",
    "secret",
)


class AgentRunInterruptResponse(BaseModel):
    id: str = Field(min_length=1, max_length=512)
    kind: str = Field(min_length=1, max_length=80)
    node: str | None = Field(default=None, max_length=160)
    resumable: bool = True


class AgentRunWorkspaceControlResponse(BaseModel):
    agent_run_id: UUID
    project_id: UUID
    thread_id: str
    graph_key: str
    graph_version: str
    code_git_sha: str
    status: str
    checkpoint_id: str | None = None
    resume_version: int = Field(ge=1)
    next_nodes: list[str]
    interrupts: list[AgentRunInterruptResponse]
    task_id: UUID | None = None
    context_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    budget_remaining: str | None = None
    route: str | None = None
    repair_iteration: int = Field(default=0, ge=0)
    max_repair_iterations: int = Field(default=0, ge=0)
    error_code: str | None = None
    updated_at: datetime


class AgentRunSafeEventResponse(BaseModel):
    event_id: str = Field(min_length=1, max_length=256)
    event_type: SafeAgentEventType
    agent_run_id: UUID
    project_id: UUID
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def reject_private_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        _assert_public_payload(value)
        return value


def _assert_public_payload(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _assert_public_payload(item)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        normalized = key.casefold()
        if normalized in _FORBIDDEN_PUBLIC_KEYS or any(
            fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS
        ):
            raise ValueError("AGENT_WORKSPACE_PRIVATE_EVENT_FIELD_FORBIDDEN")
        _assert_public_payload(item)
