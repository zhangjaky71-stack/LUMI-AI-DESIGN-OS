from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Mapping

from .ids import DomainId, new_uuid7

PROJECT_CREATED = "project.created"
ASSET_READY = "asset.ready"
AGENT_RUN_STARTED = "agent_run.started"
AGENT_RUN_WAITING_USER = "agent_run.waiting_user"
ARTIFACT_VERSION_CREATED = "artifact.version_created"
ARTIFACT_APPROVED = "artifact.approved"
TASK_SUCCEEDED = "task.succeeded"
GENERATION_COMPLETED = "generation.completed"
COST_RECORDED = "cost.recorded"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    name: str
    organization_id: DomainId
    aggregate_id: DomainId
    payload: Mapping[str, object] = field(default_factory=dict)
    event_id: DomainId = field(default_factory=new_uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("domain event name is required")
