from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from lumi_api.domain.states import (
    AgentRunStatus,
    ArtifactVersionStatus,
    GenerationStatus,
    ProjectStatus,
    TaskStatus,
)

from .common import Page, StrictModel, VersionedResource


class MoneyInput(StrictModel):
    amount: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class ProjectCreateRequest(StrictModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=240)
    brief: dict[str, Any] = Field(default_factory=dict)
    brand_id: UUID | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectPatchRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    brief: dict[str, Any] | None = None
    brand_id: UUID | None = None
    settings: dict[str, Any] | None = None


class ProjectTransitionRequest(StrictModel):
    target: ProjectStatus


class ProjectResponse(VersionedResource):
    workspace_id: UUID
    name: str
    status: ProjectStatus
    brief: dict[str, Any]
    brand_id: UUID | None = None
    active_branch_id: UUID | None = None
    settings: dict[str, Any]


class ProjectPage(Page[ProjectResponse]):
    pass


class TaskCreateRequest(StrictModel):
    task_type: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=240)
    dependency_ids: list[UUID] = Field(default_factory=list)
    priority: int = 0
    max_attempts: int = Field(default=3, ge=1, le=20)
    input: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(VersionedResource):
    project_id: UUID
    parent_task_id: UUID | None = None
    task_type: str
    name: str
    status: TaskStatus
    dependency_ids: list[UUID]
    priority: int
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    input: dict[str, Any]
    output: dict[str, Any]
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TaskPage(Page[TaskResponse]):
    pass


class AgentRunCreateRequest(StrictModel):
    goal: str = Field(min_length=1, max_length=20_000)
    budget: MoneyInput | None = None
    client_context: dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(VersionedResource):
    project_id: UUID
    thread_id: str
    graph_version: str
    agent_config_version: str
    status: AgentRunStatus
    budget: MoneyInput
    usage: dict[str, Any]
    trace_refs: list[str]


class GenerationCreateRequest(StrictModel):
    kind: Literal["image", "image_edit", "vector", "document", "video"]
    prompt: str = Field(min_length=1, max_length=50_000)
    input_asset_ids: list[UUID] = Field(default_factory=list)
    model_hint: str | None = Field(default=None, max_length=160)
    parameters: dict[str, Any] = Field(default_factory=dict)


class GenerationError(StrictModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class GenerationResponse(VersionedResource):
    project_id: UUID
    operation_id: UUID
    agent_run_id: UUID | None = None
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    status: GenerationStatus
    output_artifact_version_ids: list[UUID] = Field(default_factory=list)
    error: GenerationError | None = None


class ArtifactVersionResponse(StrictModel):
    id: UUID
    organization_id: UUID
    artifact_id: UUID
    branch_id: UUID
    version_number: int = Field(ge=1)
    status: ArtifactVersionStatus
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    quality_score: Decimal | None = Field(default=None, ge=0, le=1)
    created_by_type: str
    created_by_id: str | None = None
    created_at: datetime


class CancelResponse(StrictModel):
    accepted: bool
    status: AgentRunStatus
