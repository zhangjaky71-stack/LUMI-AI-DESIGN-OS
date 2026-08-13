from __future__ import annotations

from pathlib import Path

from lumi_agent_runtime.skill_registry import (
    SkillExecutionContext,
    SkillRegistry,
    SkillReleaseStatus,
    load_release_manifest,
    load_skills,
)
from lumi_model_gateway.models import Capability
from lumi_tool_gateway.catalog import build_p0_registry

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    definitions = load_skills(ROOT / "skills")
    manifest = load_release_manifest(ROOT / "skills/registry.json")
    registry = SkillRegistry(definitions, manifest)
    all_tools = frozenset(item.name for item in build_p0_registry().definitions())
    all_capabilities = frozenset(item.value for item in Capability)
    all_permissions = frozenset(
        permission
        for definition in definitions
        for permission in definition.permissions
    )
    by_identity = {item.identity: item for item in definitions}
    checked = 0
    for release in manifest.releases:
        if release.status != SkillReleaseStatus.PRODUCTION:
            continue
        definition = by_identity[f"{release.skill_id}@{release.version}"]
        context = SkillExecutionContext(
            agent_id=definition.compatible_agents[0],
            allowed_tools=all_tools,
            granted_permissions=all_permissions,
            available_capabilities=all_capabilities,
        )
        ref = f"{release.skill_id}@{release.version}"
        first = registry.resolve_pack((ref,), context)
        second = registry.resolve_pack((ref,), context)
        assert first.freeze_hash == second.freeze_hash
        ids = [item.definition.skill_id for item in first.skills]
        assert len(ids) == len(set(ids))
        assert first.skills[-1].definition.identity == ref
        checked += 1
    assert checked == 14
    print(f"NODE-31 production Skill packs: PASS ({checked})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
