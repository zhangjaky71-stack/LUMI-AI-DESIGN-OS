from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .envelope import EventEnvelope
from .payloads import (
    AgentRunStartedV1,
    AgentRunWaitingUserV1,
    ArtifactApprovedV1,
    ArtifactVersionCreatedV1,
    AssetReadyV1,
    CostRecordedV1,
    GenerationCompletedV1,
    ProjectCreatedV1,
    TaskSucceededV1,
)

PROJECT_CREATED_V1 = "lumi.project.created.v1"
ASSET_READY_V1 = "lumi.asset.ready.v1"
AGENT_RUN_STARTED_V1 = "lumi.agent_run.started.v1"
AGENT_RUN_WAITING_USER_V1 = "lumi.agent_run.waiting_user.v1"
TASK_SUCCEEDED_V1 = "lumi.task.succeeded.v1"
GENERATION_COMPLETED_V1 = "lumi.generation.completed.v1"
ARTIFACT_VERSION_CREATED_V1 = "lumi.artifact.version_created.v1"
ARTIFACT_APPROVED_V1 = "lumi.artifact.approved.v1"
COST_RECORDED_V1 = "lumi.cost.recorded.v1"

EVENT_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    PROJECT_CREATED_V1: ProjectCreatedV1,
    ASSET_READY_V1: AssetReadyV1,
    AGENT_RUN_STARTED_V1: AgentRunStartedV1,
    AGENT_RUN_WAITING_USER_V1: AgentRunWaitingUserV1,
    TASK_SUCCEEDED_V1: TaskSucceededV1,
    GENERATION_COMPLETED_V1: GenerationCompletedV1,
    ARTIFACT_VERSION_CREATED_V1: ArtifactVersionCreatedV1,
    ARTIFACT_APPROVED_V1: ArtifactApprovedV1,
    COST_RECORDED_V1: CostRecordedV1,
}


def parse_event(data: dict[str, Any]) -> EventEnvelope[BaseModel]:
    event_type = data.get("event_type")
    if not isinstance(event_type, str):
        raise ValueError("event_type is required")
    payload_model = EVENT_PAYLOAD_MODELS.get(event_type)
    if payload_model is None:
        raise ValueError(f"unsupported event_type: {event_type}")

    payload = payload_model.model_validate(data.get("payload"))
    normalized = dict(data)
    normalized["payload"] = payload
    return EventEnvelope[BaseModel].model_validate(normalized)
