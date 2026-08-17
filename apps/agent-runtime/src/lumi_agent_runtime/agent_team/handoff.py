from __future__ import annotations

from collections.abc import Mapping

from .contracts import HandoffStatus, TeamHandoffEnvelope, TeamRoleDefinition, TeamRoleKind


REQUIRED_STRUCTURED_KEYS: dict[str, frozenset[str]] = {
    "brief-agent": frozenset({"brief", "assumptions", "ambiguities"}),
    "research-agent": frozenset({"findings", "citations"}),
    "brand-strategy-agent": frozenset({"positioning", "audience", "message_pillars", "tone"}),
    "creative-director": frozenset({"directions"}),
    "copywriting-agent": frozenset({"variants"}),
    "typography-agent": frozenset({"typography_tokens"}),
    "layout-agent": frozenset({"operations"}),
    "image-agent": frozenset({"generation_request"}),
    "image-edit-agent": frozenset({"edit_request", "protected_constraints"}),
    "product-render-agent": frozenset({"render_request", "identity_threshold"}),
    "video-agent": frozenset({"storyboard", "shots"}),
    "critic-agent": frozenset({"critique", "repair_plan"}),
    "brand-consistency-agent": frozenset({"violations"}),
    "identity-agent": frozenset({"violations", "similarity"}),
    "export-agent": frozenset({"files"}),
}


def validate_handoff(role: TeamRoleDefinition, envelope: TeamHandoffEnvelope) -> None:
    required = REQUIRED_STRUCTURED_KEYS.get(role.agent_id, frozenset())
    missing = required - set(envelope.structured_output)
    if missing and envelope.status is HandoffStatus.SUCCEEDED:
        raise ValueError(
            "AGENT_TEAM_HANDOFF_REQUIRED_FIELDS_MISSING:"
            + role.agent_id
            + ":"
            + ",".join(sorted(missing))
        )
    if role.produces_artifacts and envelope.status is HandoffStatus.SUCCEEDED:
        if not envelope.artifact_refs and role.agent_id not in {
            "typography-agent",
            "layout-agent",
        }:
            raise ValueError(f"AGENT_TEAM_ARTIFACT_REQUIRED:{role.agent_id}")
    if role.role_kind is TeamRoleKind.CRITIC and envelope.artifact_refs:
        raise ValueError("AGENT_TEAM_CRITIC_ARTIFACT_WRITE_FORBIDDEN")
    if envelope.producer_agent_id == role.agent_id and role.role_kind is TeamRoleKind.CRITIC:
        raise ValueError("AGENT_TEAM_CRITIC_SELF_REVIEW_FORBIDDEN")


def validate_review_separation(
    *,
    producer_agent_id: str,
    reviewer_agent_id: str,
    roles: Mapping[str, TeamRoleDefinition],
) -> None:
    if producer_agent_id == reviewer_agent_id:
        raise ValueError("AGENT_TEAM_PRODUCER_REVIEWER_MUST_DIFFER")
    producer = roles[producer_agent_id]
    reviewer = roles[reviewer_agent_id]
    if producer.role_kind is not TeamRoleKind.PRODUCER:
        raise ValueError("AGENT_TEAM_REVIEW_SOURCE_NOT_PRODUCER")
    if reviewer.role_kind not in {TeamRoleKind.CRITIC, TeamRoleKind.VALIDATOR}:
        raise ValueError("AGENT_TEAM_REVIEWER_ROLE_INVALID")
