from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import Field

from .envelope import EventContractModel


class ProjectCreatedV1(EventContractModel):
    project_id: UUID
    workspace_id: UUID
    project_version: int = Field(ge=1)


class AssetReadyV1(EventContractModel):
    asset_id: UUID
    project_id: UUID | None = None
    mime_type: str = Field(min_length=3, max_length=255)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AgentRunStartedV1(EventContractModel):
    agent_run_id: UUID
    project_id: UUID
    thread_id: str = Field(min_length=1, max_length=200)
    graph_version: str = Field(min_length=1, max_length=80)
    agent_config_version: str = Field(min_length=1, max_length=80)


class AgentRunWaitingUserV1(EventContractModel):
    agent_run_id: UUID
    project_id: UUID
    interaction_id: UUID
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,79}$")


class TaskSucceededV1(EventContractModel):
    task_id: UUID
    project_id: UUID
    output_artifact_version_ids: tuple[UUID, ...] = ()


class GenerationCompletedV1(EventContractModel):
    generation_id: UUID
    project_id: UUID
    operation_id: UUID
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    output_artifact_version_ids: tuple[UUID, ...] = ()


class ArtifactVersionCreatedV1(EventContractModel):
    artifact_id: UUID
    artifact_version_id: UUID
    branch_id: UUID
    version_number: int = Field(ge=1)


class ArtifactApprovedV1(EventContractModel):
    artifact_version_id: UUID
    approval_id: UUID | None = None
    actor_id: UUID | None = None


class CostRecordedV1(EventContractModel):
    cost_entry_id: UUID
    operation_id: UUID
    amount: Decimal
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    kind: str = Field(pattern=r"^(charge|reversal|adjustment)$")
