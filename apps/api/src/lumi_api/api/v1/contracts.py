from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from lumi_domain import AgentRunStatus, ArtifactVersionStatus, ProjectStatus, TaskStatus

T = TypeVar("T")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResponseMeta(StrictModel):
    request_id: str


class PageMeta(ResponseMeta):
    next_cursor: str | None = None
    has_more: bool = False


class DataEnvelope(StrictModel, Generic[T]):
    data: T
    meta: ResponseMeta


class CollectionEnvelope(StrictModel, Generic[T]):
    data: list[T]
    meta: PageMeta


class ProblemField(StrictModel):
    field: str
    code: str
    message: str


class ProblemDetails(StrictModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str
    request_id: str
    errors: list[ProblemField] = Field(default_factory=list)


class ProjectCreate(StrictModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=300)
    brief: dict[str, Any] = Field(default_factory=dict)
    brand_id: UUID | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    status: ProjectStatus | None = None
    brief: dict[str, Any] | None = None
    brand_id: UUID | None = None
    active_branch_id: UUID | None = None
    settings: dict[str, Any] | None = None


class ProjectResource(StrictModel):
    id: UUID
    organization_id: UUID
    workspace_id: UUID
    name: str
    status: ProjectStatus
    brief: dict[str, Any] = Field(default_factory=dict)
    brand_id: UUID | None = None
    active_branch_id: UUID | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AssetCreate(StrictModel):
    project_id: UUID | None = None
    kind: str = Field(min_length=1, max_length=64)
    source: str = Field(default="upload", min_length=1, max_length=64)
    original_name: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetResource(StrictModel):
    id: UUID
    organization_id: UUID
    project_id: UUID | None = None
    kind: str
    source: str
    original_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ArtifactResource(StrictModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    kind: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ArtifactVersionCreate(StrictModel):
    branch_id: UUID
    content_hash: str = Field(min_length=1, max_length=128)
    parent_version_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by_type: Literal["user", "agent", "system"]
    created_by_id: UUID | None = None


class ArtifactVersionResource(StrictModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    artifact_id: UUID
    branch_id: UUID
    parent_version_id: UUID | None = None
    version_number: int = Field(ge=1)
    status: ArtifactVersionStatus
    content_hash: str
    quality_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AgentRunCreate(StrictModel):
    project_id: UUID
    thread_id: str = Field(min_length=1, max_length=255)
    graph_version: str = Field(min_length=1, max_length=100)
    agent_config_version: str = Field(min_length=1, max_length=100)
    budget: dict[str, Any] = Field(default_factory=dict)


class AgentRunResumeRequest(StrictModel):
    input: dict[str, Any] = Field(default_factory=dict)


class AgentRunResource(StrictModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    thread_id: str
    graph_version: str
    agent_config_version: str
    status: AgentRunStatus
    budget: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    version: int = Field(ge=1)


class TaskResource(StrictModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID | None = None
    parent_task_id: UUID | None = None
    type: str
    status: TaskStatus
    owner_agent_key: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    priority: int
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    version: int = Field(ge=1)


class GenerationCreate(StrictModel):
    project_id: UUID
    task_id: UUID | None = None
    agent_run_id: UUID | None = None
    capability: str = Field(min_length=1, max_length=100)
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=255)
    request: dict[str, Any] = Field(default_factory=dict)


class GenerationResource(StrictModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    task_id: UUID | None = None
    agent_run_id: UUID | None = None
    operation_id: UUID | None = None
    capability: str
    provider: str
    model: str
    status: str
    request: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ApprovalDecisionRequest(StrictModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalResource(StrictModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    artifact_version_id: UUID | None = None
    agent_run_id: UUID | None = None
    status: Literal["pending", "approved", "rejected"]
    reason: str | None = None
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    version: int = Field(ge=1)


class HealthResource(StrictModel):
    status: Literal["ok"] = "ok"
    api_version: Literal["v1"] = "v1"
