from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

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
