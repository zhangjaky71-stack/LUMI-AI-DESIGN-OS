from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SRC = ROOT / "apps/agent-runtime/src"
sys.path.insert(0, str(RUNTIME_SRC))

from lumi_agent_runtime.agent_team import (  # noqa: E402
    CANONICAL_AGENT_IDS,
    CORE_50_AGENT_IDS,
    DEFAULT_TEAM,
    SPECIALIZED_AGENT_IDS,
    DelegationPolicy,
    build_coffee_poster_mock_plan,
    build_eval_profiles,
)


def main() -> None:
    if len(CANONICAL_AGENT_IDS) != 17:
        raise SystemExit("NODE37_ROLE_COUNT_INVALID")
    if len(SPECIALIZED_AGENT_IDS) != 16:
        raise SystemExit("NODE37_SPECIALIST_COUNT_INVALID")
    if tuple(DEFAULT_TEAM) != CANONICAL_AGENT_IDS:
        raise SystemExit("NODE37_CANONICAL_ORDER_INVALID")

    manifests = tuple(role.to_agent_manifest() for role in DEFAULT_TEAM.values())
    if len(manifests) != 17:
        raise SystemExit("NODE37_MANIFEST_COUNT_INVALID")
    if any(manifest.subagent_refs for manifest in manifests):
        raise SystemExit("NODE37_REGISTRY_SUBAGENT_ESCALATION_PATH_FORBIDDEN")

    director = DEFAULT_TEAM["director"]
    forbidden_direct = {
        "model.generate.image",
        "model.edit.image",
        "model.generate.video",
        "artifact.write-derived",
    }
    if forbidden_direct & set(director.direct_tools):
        raise SystemExit("NODE37_DIRECTOR_SPECIALIST_TOOL_LEAK")

    DelegationPolicy(DEFAULT_TEAM)
    plan = build_coffee_poster_mock_plan()
    if len(plan.steps) != 9:
        raise SystemExit("NODE37_MOCK_FLOW_INVALID")

    profiles = build_eval_profiles(DEFAULT_TEAM)
    if set(profiles) != set(CANONICAL_AGENT_IDS):
        raise SystemExit("NODE37_EVAL_COVERAGE_INVALID")
    for agent_id, profile in profiles.items():
        expected = 50 if agent_id in CORE_50_AGENT_IDS else 20
        if len(profile.cases) != expected:
            raise SystemExit(f"NODE37_EVAL_CASE_COUNT_INVALID:{agent_id}")

    critic = DEFAULT_TEAM["critic-agent"]
    if critic.produces_artifacts:
        raise SystemExit("NODE37_CRITIC_PRODUCER_SEPARATION_INVALID")
    if "artifact.write-derived" in critic.direct_tools:
        raise SystemExit("NODE37_CRITIC_WRITE_TOOL_FORBIDDEN")

    print("NODE37_AGENT_TEAM_VALIDATION_PASS")
    print("roles=17")
    print("specialists=16")
    print("eval_cases=490")
    print("mock_flow_steps=9")


if __name__ == "__main__":
    main()
