from __future__ import annotations

import ast
import json
from pathlib import Path

from lumi_agent_runtime.agent_team.evals import (
    load_role_eval_contracts,
    validate_role_eval_bindings,
)
from lumi_agent_runtime.agent_team.registry import (
    CANONICAL_AGENT_IDS,
    compile_agent_team,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/agent_team"
TEAM_MANIFEST = ROOT / "config/agent-team/team.v1.json"
DEPENDENCIES = ROOT / "config/agent-registry/bootstrap-dependencies.v1.json"
ROUTES = ROOT / "docs/models/route-candidates.json"
TOOL_NAMES = {
    "web.search",
    "web.fetch",
    "asset.read",
    "asset.write-derived",
    "project.query",
    "artifact.query",
    "sandbox.execute",
    "media.inspect",
}
REQUIRED_MODULES = {
    "__init__.py",
    "contracts.py",
    "delegation.py",
    "evals.py",
    "flow.py",
    "handoff.py",
    "registry.py",
}


def main() -> int:
    missing = sorted(name for name in REQUIRED_MODULES if not (PACKAGE / name).is_file())
    if missing:
        raise SystemExit(f"NODE-37 Agent Team modules missing: {missing}")

    team = compile_agent_team(repo_root=ROOT)
    if tuple(team.definitions) != CANONICAL_AGENT_IDS:
        raise SystemExit("NODE-37 canonical 16-agent set drifted")
    if len(team.definitions) != 16:
        raise SystemExit("NODE-37 must contain exactly 16 team definitions")

    dependency_payload = json.loads(DEPENDENCIES.read_text(encoding="utf-8"))
    skills = set(dependency_payload["skills"])
    contexts = set(dependency_payload["context_policies"])
    budgets = set(dependency_payload["budget_policies"])
    outputs = set(dependency_payload["output_schemas"])
    eval_profiles = set(dependency_payload["eval_profiles"])
    route_payload = json.loads(ROUTES.read_text(encoding="utf-8"))
    route_text = json.dumps(route_payload, ensure_ascii=False)

    for agent_id, definition in team.definitions.items():
        if definition.version != "2.0.0":
            raise SystemExit(f"NODE-37 team version drift: {agent_id}")
        if definition.context_policy not in contexts:
            raise SystemExit(f"NODE-37 unknown context policy: {agent_id}")
        if definition.budget_policy not in budgets:
            raise SystemExit(f"NODE-37 unknown budget policy: {agent_id}")
        if definition.output_schema not in outputs:
            raise SystemExit(f"NODE-37 unknown output schema: {agent_id}")
        if definition.eval_profile not in eval_profiles:
            raise SystemExit(f"NODE-37 unknown eval profile: {agent_id}")
        if f'"{definition.model_policy}"' not in route_text:
            raise SystemExit(f"NODE-37 unknown model route: {agent_id}:{definition.model_policy}")
        for skill in definition.skills:
            if skill.id not in skills:
                raise SystemExit(f"NODE-37 unknown skill: {agent_id}:{skill.id}")
        unknown_tools = set(definition.allowed_tools) - TOOL_NAMES
        if unknown_tools:
            raise SystemExit(
                f"NODE-37 unknown tools: {agent_id}:" + ",".join(sorted(unknown_tools))
            )
        prompt_path = ROOT / f"agents/{agent_id}/2.0.0/system.md"
        if not prompt_path.is_file() or not prompt_path.read_text(encoding="utf-8").strip():
            raise SystemExit(f"NODE-37 missing system prompt: {agent_id}")

    contracts = load_role_eval_contracts(
        ROOT / "evals/profiles/agents/agent-team-v1.json"
    )
    validate_role_eval_bindings(team, contracts)

    _require_markers(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_team/contracts.py",
        "TeamTaskInput",
        "TeamTaskResult",
        "WAITING_EXTERNAL",
        "WAITING_APPROVAL",
        "delegation_tool_ceiling",
        "delegation_permission_ceiling",
    )
    _require_markers(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_team/delegation.py",
        "AGENT_TEAM_CHILD_TOOL_ESCALATION",
        "AGENT_TEAM_CHILD_PERMISSION_ESCALATION",
        "AGENT_TEAM_DELEGATION_DEPTH_EXCEEDED",
        "AGENT_TEAM_DELEGATION_CANCELLED",
    )
    _require_markers(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_team/handoff.py",
        "AGENT_TEAM_HANDOFF_BUDGET_MISMATCH",
        "AGENT_TEAM_HANDOFF_DEADLINE_MISMATCH",
        "AGENT_TEAM_RESULT_UNKNOWN_FIELDS",
        "AGENT_TEAM_CRITIC_CANNOT_RETURN_WRITTEN_ARTIFACT",
    )
    flow = _require_markers(
        "apps/agent-runtime/src/lumi_agent_runtime/agent_team/flow.py",
        "brand-strategist",
        "research-agent",
        "prompt-engineer",
        "image-generator",
        "critic-agent",
        "image-editor",
        "WAITING_EXTERNAL",
        "FAILED_RETRYABLE",
    )
    if "while True" in flow:
        raise SystemExit("NODE-37 flow contains unbounded loop")

    critic = team.resolve("critic-agent")
    if {"asset.write-derived", "sandbox.execute"} & set(critic.allowed_tools):
        raise SystemExit("NODE-37 Critic has a write-capable tool")
    if any("write" in permission for permission in critic.permissions):
        raise SystemExit("NODE-37 Critic has a write permission")
    brand = team.profiles["brand-strategist"]
    if "brand-rule.write" not in brand.approval_gated_actions:
        raise SystemExit("NODE-37 BrandRule write is not approval-gated")
    for video_id in ("video-generator", "video-editor"):
        if not team.profiles[video_id].supports_waiting_external:
            raise SystemExit(f"NODE-37 {video_id} lacks waiting-external support")

    schema = json.loads(
        (ROOT / "schemas/agent-outputs/team-task-result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    if schema.get("additionalProperties") is not False:
        raise SystemExit("NODE-37 TeamTaskResult schema is not strict")
    required = set(schema.get("required", []))
    if not {
        "status",
        "summary",
        "artifacts",
        "citations",
        "confidence",
        "warnings",
        "followups",
        "structured_output",
    } <= required:
        raise SystemExit("NODE-37 TeamTaskResult required fields drifted")

    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AgentDefinition":
                raise SystemExit("NODE-37 creates a competing AgentDefinition")

    # NODE-37 intentionally pins candidate versions in its team manifest. It does
    # not rewrite the NODE-28 production release registry in this node.
    production_registry = json.loads(
        (ROOT / "agents/registry.json").read_text(encoding="utf-8")
    )
    production_text = json.dumps(production_registry, ensure_ascii=False)
    if "2.0.0" in production_text:
        raise SystemExit("NODE-37 silently promoted team candidates in production registry")

    print("NODE-37 Agent Team static contract: PASS")
    return 0


def _require_markers(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"{path}: missing NODE-37 marker: {marker}")
    return text


if __name__ == "__main__":
    raise SystemExit(main())
