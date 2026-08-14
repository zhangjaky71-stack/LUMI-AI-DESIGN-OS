from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lumi_agent_runtime.agent_registry.definition import AgentDefinition

from .registry import CANONICAL_AGENT_IDS, CompiledAgentTeam


@dataclass(frozen=True, slots=True)
class RoleEvalContract:
    agent_id: str
    must: tuple[str, ...]
    forbid: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.agent_id or not self.must:
            raise ValueError("AGENT_TEAM_ROLE_EVAL_INVALID")
        if len(set(self.must)) != len(self.must) or len(set(self.forbid)) != len(self.forbid):
            raise ValueError("AGENT_TEAM_ROLE_EVAL_DUPLICATE")


def load_role_eval_contracts(path: Path) -> dict[str, RoleEvalContract]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != "lumi.agent-team-role-evals.v1":
        raise ValueError("AGENT_TEAM_ROLE_EVAL_SCHEMA_INVALID")
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        raise ValueError("AGENT_TEAM_ROLE_EVAL_ROLES_INVALID")
    if tuple(roles) != CANONICAL_AGENT_IDS:
        raise ValueError("AGENT_TEAM_ROLE_EVAL_MEMBER_SET_INVALID")
    contracts: dict[str, RoleEvalContract] = {}
    for agent_id, raw in roles.items():
        if not isinstance(raw, dict):
            raise ValueError(f"AGENT_TEAM_ROLE_EVAL_ENTRY_INVALID:{agent_id}")
        must = raw.get("must")
        forbid = raw.get("forbid")
        if not isinstance(must, list) or not isinstance(forbid, list):
            raise ValueError(f"AGENT_TEAM_ROLE_EVAL_LIST_INVALID:{agent_id}")
        contracts[agent_id] = RoleEvalContract(
            agent_id=agent_id,
            must=tuple(str(item) for item in must),
            forbid=tuple(str(item) for item in forbid),
        )
    return contracts


def validate_role_eval_bindings(
    team: CompiledAgentTeam,
    contracts: dict[str, RoleEvalContract],
) -> None:
    if set(contracts) != set(team.definitions):
        raise ValueError("AGENT_TEAM_ROLE_EVAL_BINDING_SET_INVALID")
    for agent_id, definition in team.definitions.items():
        expected = f"team-{agent_id}-v1"
        if definition.eval_profile != expected:
            raise ValueError(f"AGENT_TEAM_ROLE_EVAL_PROFILE_MISMATCH:{agent_id}")
        _validate_role_static_contract(definition, contracts[agent_id])


def _validate_role_static_contract(
    definition: AgentDefinition,
    contract: RoleEvalContract,
) -> None:
    """Static safety/definition checks only; this is not a semantic model-quality score."""
    text = "\n".join(
        (
            definition.role,
            definition.prompt.text,
            json.dumps(definition.metadata, ensure_ascii=False, sort_keys=True),
            " ".join(definition.allowed_tools),
            " ".join(definition.permissions),
        )
    ).casefold()
    safety_markers = {
        "delegate_only_allowlist": ("allowlist", "delegate"),
        "remain_read_only": ("read-only",),
        "silent_brand_rule_write": ("approval",),
        "write_artifact": ("read-only",),
        "mutate_asset": ("read-only",),
        "fake_completed_video": ("waiting_external", "completion"),
        "fake_completed_edit": ("waiting_external", "completion"),
        "fabricate_metric": ("fabricat",),
    }
    for criterion in (*contract.must, *contract.forbid):
        markers = safety_markers.get(criterion)
        if markers and not all(marker in text for marker in markers):
            raise ValueError(
                f"AGENT_TEAM_ROLE_STATIC_CONTRACT_MISSING:{definition.agent_id}:{criterion}"
            )
