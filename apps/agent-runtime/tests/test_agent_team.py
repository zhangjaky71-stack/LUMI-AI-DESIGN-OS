from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from lumi_agent_runtime.agent_team.contracts import (
    TeamTaskInput,
    TeamTaskResult,
    TeamTaskStatus,
    team_profile,
)
from lumi_agent_runtime.agent_team.delegation import (
    DelegationRuntimeContext,
    authorize_delegation,
)
from lumi_agent_runtime.agent_team.evals import (
    load_role_eval_contracts,
    validate_role_eval_bindings,
)
from lumi_agent_runtime.agent_team.handoff import (
    build_handoff,
    parse_team_task_result,
    validate_result_for_agent,
)
from lumi_agent_runtime.agent_team.registry import (
    CANONICAL_AGENT_IDS,
    P0_AGENT_IDS,
    P1_AGENT_IDS,
    compile_agent_team,
)

ROOT = Path(__file__).resolve().parents[3]


class AgentTeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.team = compile_agent_team(repo_root=ROOT)

    def test_exact_canonical_16_agents_and_tiers(self) -> None:
        self.assertEqual(tuple(self.team.definitions), CANONICAL_AGENT_IDS)
        self.assertEqual(len(P0_AGENT_IDS), 8)
        self.assertEqual(len(P1_AGENT_IDS), 8)
        self.assertEqual(self.team.manifest.root_agent, "creative-director")
        self.assertEqual(
            self.team.manifest.image_flow,
            (
                "creative-director",
                "brand-strategist",
                "research-agent",
                "prompt-engineer",
                "image-generator",
                "critic-agent",
                "image-editor",
            ),
        )

    def test_every_definition_uses_team_task_result_and_team_profile(self) -> None:
        for agent_id, definition in self.team.definitions.items():
            self.assertEqual(definition.version, "2.0.0")
            self.assertEqual(definition.output_schema, "TeamTaskResult")
            profile = team_profile(definition)
            self.assertTrue(profile.objective)
            self.assertTrue(definition.prompt.text.strip())
            self.assertTrue(definition.model_policy)
            self.assertTrue(definition.eval_profile.startswith("team-"))
            self.assertFalse(definition.memory_policy.get("write", []), agent_id)

    def test_role_static_eval_bindings_cover_all_16(self) -> None:
        contracts = load_role_eval_contracts(
            ROOT / "evals/profiles/agents/agent-team-v1.json"
        )
        validate_role_eval_bindings(self.team, contracts)
        self.assertEqual(set(contracts), set(CANONICAL_AGENT_IDS))

    def test_critic_is_source_level_read_only(self) -> None:
        critic = self.team.resolve("critic-agent")
        profile = team_profile(critic)
        self.assertEqual(profile.archetype.value, "critic")
        self.assertEqual(profile.risk_profile, "read-only")
        self.assertNotIn("asset.write-derived", critic.allowed_tools)
        self.assertNotIn("sandbox.execute", critic.allowed_tools)
        self.assertFalse(any("write" in permission for permission in critic.permissions))

    def test_brand_write_is_approval_gated(self) -> None:
        brand = self.team.resolve("brand-strategist")
        self.assertIn(
            "brand-rule.write",
            team_profile(brand).approval_gated_actions,
        )
        validate_result_for_agent(
            brand,
            TeamTaskResult(
                status=TeamTaskStatus.WAITING_APPROVAL,
                summary="Brand rule proposal needs approval",
                confidence=0.9,
                waiting_reason="brand-rule.write",
            ),
        )

    def test_video_workers_support_external_wait_but_regular_agent_does_not(self) -> None:
        waiting = TeamTaskResult(
            status=TeamTaskStatus.WAITING_EXTERNAL,
            summary="Provider job accepted",
            confidence=0.8,
            waiting_reason="provider-request:123",
        )
        validate_result_for_agent(self.team.resolve("video-generator"), waiting)
        validate_result_for_agent(self.team.resolve("video-editor"), waiting)
        with self.assertRaisesRegex(
            ValueError,
            "AGENT_TEAM_WAITING_EXTERNAL_NOT_SUPPORTED",
        ):
            validate_result_for_agent(self.team.resolve("prompt-engineer"), waiting)

    def test_delegation_grant_narrows_to_child_tools_and_permissions(self) -> None:
        parent = self.team.resolve("creative-director")
        child = self.team.resolve("image-editor")
        parent_profile = team_profile(parent)
        runtime = DelegationRuntimeContext(
            allowed_tools=parent_profile.delegation_tool_ceiling,
            granted_permissions=parent_profile.delegation_permission_ceiling,
            depth=0,
            budget_remaining_usd=12.5,
            deadline_at=datetime(2026, 8, 14, 18, 0, tzinfo=UTC),
        )
        grant = authorize_delegation(
            parent=parent,
            child=child,
            runtime=runtime,
        )
        self.assertEqual(grant.allowed_tools, frozenset(child.allowed_tools))
        self.assertEqual(grant.granted_permissions, frozenset(child.permissions))
        self.assertEqual(grant.remaining_depth, 0)
        self.assertEqual(grant.budget_remaining_usd, 12.5)
        self.assertEqual(grant.deadline_at, runtime.deadline_at)

    def test_cancel_and_depth_are_hard_delegation_stops(self) -> None:
        parent = self.team.resolve("creative-director")
        child = self.team.resolve("research-agent")
        profile = team_profile(parent)
        with self.assertRaisesRegex(PermissionError, "AGENT_TEAM_DELEGATION_CANCELLED"):
            authorize_delegation(
                parent=parent,
                child=child,
                runtime=DelegationRuntimeContext(
                    allowed_tools=profile.delegation_tool_ceiling,
                    granted_permissions=profile.delegation_permission_ceiling,
                    depth=0,
                    cancelled=True,
                ),
            )
        with self.assertRaisesRegex(
            PermissionError,
            "AGENT_TEAM_DELEGATION_DEPTH_EXCEEDED",
        ):
            authorize_delegation(
                parent=parent,
                child=child,
                runtime=DelegationRuntimeContext(
                    allowed_tools=profile.delegation_tool_ceiling,
                    granted_permissions=profile.delegation_permission_ceiling,
                    depth=1,
                ),
            )

    def test_handoff_propagates_budget_deadline_and_no_hidden_reasoning(self) -> None:
        parent = self.team.resolve("creative-director")
        child = self.team.resolve("prompt-engineer")
        profile = team_profile(parent)
        deadline = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
        task = TeamTaskInput(
            objective="Translate brief to generation spec",
            inputs={"brief": {"title": "Launch poster"}},
            constraints=("Preserve logo",),
            expected_output="Structured generation spec",
            deadline_at=deadline,
            budget_remaining_usd=6.0,
            trace_id="trace-37",
        )
        handoff = build_handoff(
            parent=parent,
            child=child,
            task=task,
            runtime=DelegationRuntimeContext(
                allowed_tools=profile.delegation_tool_ceiling,
                granted_permissions=profile.delegation_permission_ceiling,
                depth=0,
                budget_remaining_usd=6.0,
                deadline_at=deadline,
            ),
        )
        self.assertEqual(handoff.task.budget_remaining_usd, 6.0)
        self.assertEqual(handoff.task.deadline_at, deadline)
        self.assertNotIn("reasoning", handoff.task.inputs)
        self.assertNotIn("chain_of_thought", handoff.task.inputs)

    def test_result_parser_is_strict_and_critic_cannot_return_written_artifact(self) -> None:
        payload = {
            "status": "SUCCEEDED",
            "summary": "Candidate meets most brief constraints",
            "artifacts": [],
            "citations": [],
            "confidence": 0.8,
            "warnings": ["Typography needs refinement"],
            "followups": [],
            "structured_output": {"score": 0.8},
        }
        result = parse_team_task_result(payload)
        validate_result_for_agent(self.team.resolve("critic-agent"), result)
        with self.assertRaisesRegex(ValueError, "AGENT_TEAM_RESULT_UNKNOWN_FIELDS"):
            parse_team_task_result({**payload, "hidden_reasoning": "forbidden"})
        bad = TeamTaskResult(
            status=TeamTaskStatus.SUCCEEDED,
            summary="Critique that illegally claims a new artifact",
            artifacts=(),
            confidence=0.5,
        )
        validate_result_for_agent(self.team.resolve("critic-agent"), bad)


if __name__ == "__main__":
    unittest.main()
