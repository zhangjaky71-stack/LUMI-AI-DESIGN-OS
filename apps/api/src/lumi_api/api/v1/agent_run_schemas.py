from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AgentRunResumeRequest(BaseModel):
    operation_id: UUID
    resume_version: int = Field(ge=1)
    interrupt_id: str = Field(min_length=1, max_length=512)
    kind: Literal["approval", "external_job", "input"]
    value: Any


class AgentRunCancelRequest(BaseModel):
    operation_id: UUID


class AgentRunControlResponse(BaseModel):
    agent_run_id: UUID
    thread_id: str
    graph_key: str
    graph_version: str
    code_git_sha: str
    status: str
    checkpoint_id: str | None = None
    resume_version: int
    next_nodes: list[str]
    interrupts: list[dict[str, Any]]
