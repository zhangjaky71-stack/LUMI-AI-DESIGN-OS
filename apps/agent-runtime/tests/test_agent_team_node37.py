from __future__ import annotations

import pytest

from lumi_agent_runtime.agent_team import (
    CANONICAL_AGENT_IDS,
    CORE_50_AGENT_IDS,
    DEFAULT_TEAM,
    SPECIALIZED_AGENT_IDS,
    DelegationPolicy,
    DelegationRequest,
    HandoffStatus,
    PosterFlowStage,
    TeamHandoffEnvelope,
    TeamRoleKind,
    build_coffee_poster_mock_plan,
    build_eval_profiles,
    validate_handoff,
    validate_review_separation,
)


def test_topology_is_16_specialists_plus_one_director() -> None:
    assert len(SPECIALIZED_AGENT_IDS) == 16
    assert len(CANONICAL_AGENT_IDS) == 17
    assert CANONICAL_AGENT_IDS[0] == "director"
    assert tuple(DEFAULT_TEAM) == CANONICAL_AGENT_IDS


def test_every_role_compiles_to_current_agent_manifest_contract() -> None:
    manifests = tuple(role.to_agent_manifest() for role in DEFAULT_TEAM.values())
    assert len(manifests) == 17
    assert {manifest.agent_id for manifest in manifests} == set(CANONICAL_AGENT_IDS)
    assert all(manifest.output_schema == "TeamHandoffEnvelope" for manifest in manifests)


def test_director_has_only_control_plane_tools() -> None:
    director = DEFAULT_TEAM["director"]
    assert director.role_kind is TeamRoleKind.DIRECTOR
    assert set(director.direct_tools) == {
        "project.query",
        "task.query",
        "artifact.query",
        "agent.delegate",
    }
    assert "model.generate.image" not in director.direct_tools
    assert "model.generate.video" not in director.direct_tools
    assert "artifact.write-derived" not in director.direct_tools


def test_only_director_can_delegate() -> None:
    delegators = [role.agent_id for role in DEFAULT_TEAM.values() if role.can_delegate]
    assert delegators == ["director"]
    assert set(DEFAULT_TEAM["director"].delegation_allowlist) == set(SPECIALIZED_AGENT_IDS)


def test_delegation_effective_tools_are_child_and_invocation_intersection() -> None:
    policy = DelegationPolicy(DEFAULT_TEAM)
    grant = policy.authorize(
        DelegationRequest(
            parent_agent_id="director",
            child_agent_id="image-agent",
            invocation_tools=frozenset(
                {
                    "asset.query",
                    "model.generate.image",
                    "artifact.write-derived",
                    "web.search",
                }
            ),
            remaining_depth=1,
            objective="Generate a coffee hero image",
            budget_remaining_usd=3.0,
        )
    )
    assert grant.effective_tools == frozenset(
        {"asset.query", "model.generate.image", "artifact.write-derived"}
    )
    assert "web.search" not in grant.effective_tools
    assert grant.remaining_depth == 0


def test_specialist_to_specialist_delegation_is_forbidden() -> None:
    policy = DelegationPolicy(DEFAULT_TEAM)
    with pytest.raises(PermissionError, match="AGENT_TEAM_SPECIALIST_DELEGATION_FORBIDDEN"):
        policy.authorize(
            DelegationRequest(
                parent_agent_id="image-agent",
                child_agent_id="critic-agent",
                invocation_tools=frozenset({"artifact.query", "quality.evaluate"}),
                remaining_depth=1,
                objective="Review my own output",
            )
        )


def test_delegation_cannot_gain_tool_not_granted_by_invocation() -> None:
    policy = DelegationPolicy(DEFAULT_TEAM)
    grant = policy.authorize(
        DelegationRequest(
            parent_agent_id="director",
            child_agent_id="research-agent",
            invocation_tools=frozenset({"knowledge.search", "web.search"}),
            remaining_depth=1,
            objective="Research coffee poster visual trends",
        )
    )
    assert grant.effective_tools == frozenset({"knowledge.search", "web.search"})
    assert "web.fetch" not in grant.effective_tools


def test_successful_brief_handoff_requires_structured_fields() -> None:
    envelope = TeamHandoffEnvelope(
        status=HandoffStatus.SUCCEEDED,
        summary="Brief ready",
        structured_output={"brief": {}, "assumptions": [], "ambiguities": []},
        confidence=0.9,
    )
    validate_handoff(DEFAULT_TEAM["brief-agent"], envelope)


def test_successful_brief_handoff_rejects_missing_machine_field() -> None:
    envelope = TeamHandoffEnvelope(
        status=HandoffStatus.SUCCEEDED,
        summary="Brief ready",
        structured_output={"brief": {}},
        confidence=0.9,
    )
    with pytest.raises(ValueError, match="AGENT_TEAM_HANDOFF_REQUIRED_FIELDS_MISSING"):
        validate_handoff(DEFAULT_TEAM["brief-agent"], envelope)


def test_critic_cannot_emit_artifact_write() -> None:
    envelope = TeamHandoffEnvelope(
        status=HandoffStatus.SUCCEEDED,
        summary="Critique complete",
        structured_output={"critique": [], "repair_plan": []},
        artifact_refs=("artifact://critic-output",),
        confidence=0.8,
    )
    with pytest.raises(ValueError, match="AGENT_TEAM_CRITIC_ARTIFACT_WRITE_FORBIDDEN"):
        validate_handoff(DEFAULT_TEAM["critic-agent"], envelope)


def test_producer_and_reviewer_are_separate_roles() -> None:
    validate_review_separation(
        producer_agent_id="image-agent",
        reviewer_agent_id="critic-agent",
        roles=DEFAULT_TEAM,
    )
    with pytest.raises(ValueError, match="AGENT_TEAM_PRODUCER_REVIEWER_MUST_DIFFER"):
        validate_review_separation(
            producer_agent_id="image-agent",
            reviewer_agent_id="image-agent",
            roles=DEFAULT_TEAM,
        )


def test_brand_rule_write_is_approval_gated() -> None:
    role = DEFAULT_TEAM["brand-strategy-agent"]
    assert "brand-rule.write" in role.approval_gated_actions


def test_layout_agent_cannot_bypass_constraint_engine() -> None:
    tools = set(DEFAULT_TEAM["layout-agent"].direct_tools)
    assert "design-ir.propose" in tools
    assert "constraint.validate" in tools
    assert "renderer.write" not in tools


def test_mock_coffee_poster_flow_matches_required_stage_order() -> None:
    plan = build_coffee_poster_mock_plan()
    assert tuple(step.stage for step in plan.steps) == (
        PosterFlowStage.BRIEF,
        PosterFlowStage.RESEARCH,
        PosterFlowStage.CREATIVE_DIRECTION,
        PosterFlowStage.APPROVAL,
        PosterFlowStage.PRODUCTION,
        PosterFlowStage.REVIEW,
        PosterFlowStage.REPAIR,
        PosterFlowStage.EXPORT,
        PosterFlowStage.COMPLETE,
    )
    assert plan.steps[3].approval_required is True
    assert plan.steps[4].parallel is True
    assert plan.steps[5].parallel is True


def test_eval_profiles_cover_all_roles_and_core_50_case_requirement() -> None:
    profiles = build_eval_profiles(DEFAULT_TEAM)
    assert set(profiles) == set(CANONICAL_AGENT_IDS)
    for agent_id, profile in profiles.items():
        expected = 50 if agent_id in CORE_50_AGENT_IDS else 20
        assert profile.minimum_cases == expected
        assert len(profile.cases) == expected
    assert sum(len(profile.cases) for profile in profiles.values()) == 490
