from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lumi_agent_runtime.agent_registry.definition import AgentDefinition

from .contracts import (
    DelegationGrant,
    TeamArtifactRef,
    TeamCitationRef,
    TeamTaskInput,
    TeamTaskResult,
    TeamTaskStatus,
    team_profile,
)
from .delegation import DelegationRuntimeContext, authorize_delegation


@dataclass(frozen=True, slots=True)
class TeamHandoff:
    parent_agent: str
    child_agent: str
    task: TeamTaskInput
    grant: DelegationGrant


def build_handoff(
    *,
    parent: AgentDefinition,
    child: AgentDefinition,
    task: TeamTaskInput,
    runtime: DelegationRuntimeContext,
) -> TeamHandoff:
    grant = authorize_delegation(parent=parent, child=child, runtime=runtime)
    if task.budget_remaining_usd != runtime.budget_remaining_usd:
        raise ValueError("AGENT_TEAM_HANDOFF_BUDGET_MISMATCH")
    if task.deadline_at != runtime.deadline_at:
        raise ValueError("AGENT_TEAM_HANDOFF_DEADLINE_MISMATCH")
    return TeamHandoff(
        parent_agent=parent.agent_id,
        child_agent=child.agent_id,
        task=task,
        grant=grant,
    )


def parse_team_task_result(payload: dict[str, Any]) -> TeamTaskResult:
    allowed = {
        "status",
        "summary",
        "artifacts",
        "citations",
        "confidence",
        "warnings",
        "followups",
        "waiting_reason",
        "structured_output",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError("AGENT_TEAM_RESULT_UNKNOWN_FIELDS:" + ",".join(sorted(unknown)))
    artifacts_raw = payload.get("artifacts", [])
    citations_raw = payload.get("citations", [])
    warnings_raw = payload.get("warnings", [])
    followups_raw = payload.get("followups", [])
    structured = payload.get("structured_output", {})
    if not isinstance(artifacts_raw, list) or not isinstance(citations_raw, list):
        raise ValueError("AGENT_TEAM_RESULT_REFERENCE_LIST_INVALID")
    if not isinstance(warnings_raw, list) or not isinstance(followups_raw, list):
        raise ValueError("AGENT_TEAM_RESULT_STRING_LIST_INVALID")
    if not isinstance(structured, dict):
        raise ValueError("AGENT_TEAM_RESULT_STRUCTURED_OUTPUT_INVALID")
    artifacts = tuple(
        TeamArtifactRef(
            artifact_id=_field(item, "artifact_id"),
            version=_field(item, "version"),
            kind=_field(item, "kind"),
        )
        for item in artifacts_raw
        if isinstance(item, dict)
    )
    citations = tuple(
        TeamCitationRef(
            source_type=_field(item, "source_type"),
            source_id=_field(item, "source_id"),
            version=_field(item, "version"),
            locator=_object_field(item, "locator"),
        )
        for item in citations_raw
        if isinstance(item, dict)
    )
    if len(artifacts) != len(artifacts_raw) or len(citations) != len(citations_raw):
        raise ValueError("AGENT_TEAM_RESULT_REFERENCE_OBJECT_INVALID")
    waiting_reason = payload.get("waiting_reason")
    if waiting_reason is not None and not isinstance(waiting_reason, str):
        raise ValueError("AGENT_TEAM_RESULT_WAITING_REASON_INVALID")
    return TeamTaskResult(
        status=TeamTaskStatus(_field(payload, "status")),
        summary=_field(payload, "summary"),
        artifacts=artifacts,
        citations=citations,
        confidence=float(payload.get("confidence", 0.0)),
        warnings=tuple(str(item) for item in warnings_raw),
        followups=tuple(str(item) for item in followups_raw),
        waiting_reason=waiting_reason,
        structured_output=structured,
    )


def validate_result_for_agent(
    definition: AgentDefinition,
    result: TeamTaskResult,
) -> None:
    profile = team_profile(definition)
    if result.status == TeamTaskStatus.WAITING_EXTERNAL:
        if not profile.supports_waiting_external:
            raise ValueError("AGENT_TEAM_WAITING_EXTERNAL_NOT_SUPPORTED")
    if result.status == TeamTaskStatus.WAITING_APPROVAL:
        if not profile.approval_gated_actions:
            raise ValueError("AGENT_TEAM_WAITING_APPROVAL_NOT_SUPPORTED")
    if profile.archetype.value == "critic" and result.artifacts:
        raise ValueError("AGENT_TEAM_CRITIC_CANNOT_RETURN_WRITTEN_ARTIFACT")


def result_to_payload(result: TeamTaskResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "summary": result.summary,
        "artifacts": [
            {
                "artifact_id": item.artifact_id,
                "version": item.version,
                "kind": item.kind,
            }
            for item in result.artifacts
        ],
        "citations": [
            {
                "source_type": item.source_type,
                "source_id": item.source_id,
                "version": item.version,
                "locator": item.locator,
            }
            for item in result.citations
        ],
        "confidence": result.confidence,
        "warnings": list(result.warnings),
        "followups": list(result.followups),
        "waiting_reason": result.waiting_reason,
        "structured_output": result.structured_output,
    }


def _field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AGENT_TEAM_RESULT_FIELD_INVALID:{key}")
    return value


def _object_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"AGENT_TEAM_RESULT_OBJECT_FIELD_INVALID:{key}")
    return value
