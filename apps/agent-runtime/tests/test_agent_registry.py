from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lumi_agent_runtime.agent_registry import (
    AgentDependencyError,
    AgentRegistry,
    AgentValidator,
    CatalogEntry,
    DependencyResolver,
    SkillRequirement,
    StaticNamedCatalog,
    StaticSystemPromptLinter,
    StaticVersionedCatalog,
    load_bootstrap_catalog,
    load_definitions,
    load_release_manifest,
    select_highest,
    to_deep_agent_definition,
)

ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP = ROOT / "config/agent-registry/bootstrap-dependencies.v1.json"


def _dependencies() -> DependencyResolver:
    names = ("web.search", "web.fetch", "asset.read", "artifact.query", "media.inspect")
    tools = StaticVersionedCatalog({
        name: (CatalogEntry(name, "1.0.0", f"hash:{name}", f"NODE-25:{name}@1.0.0"),)
        for name in names
    })
    models = StaticNamedCatalog({
        name: CatalogEntry(name, "registry-1", "model-registry-hash", f"NODE-23:{name}")
        for name in ("reasoning.director", "reasoning.default")
    })
    return DependencyResolver(
        model_policies=models,
        tools=tools,
        skills=load_bootstrap_catalog(BOOTSTRAP, "skills"),
        context_policies=load_bootstrap_catalog(BOOTSTRAP, "context_policies"),
        budget_policies=load_bootstrap_catalog(BOOTSTRAP, "budget_policies"),
        output_schemas=load_bootstrap_catalog(BOOTSTRAP, "output_schemas"),
        eval_profiles=load_bootstrap_catalog(BOOTSTRAP, "eval_profiles"),
    )


def _registry() -> AgentRegistry:
    return AgentRegistry(
        load_definitions(ROOT / "agents"),
        load_release_manifest(ROOT / "agents/registry.json"),
        AgentValidator(dependencies=_dependencies()),
    )


class AgentRegistryTests(unittest.TestCase):
    def test_semver_resolves_highest_compatible_version(self) -> None:
        self.assertEqual(select_highest(("1.0.0", "1.9.0", "2.0.0"), "^1"), "1.9.0")
        self.assertEqual(select_highest(("1.2.0", "1.2.9", "1.3.0"), "~1.2"), "1.2.9")

    def test_range_selects_production_not_newer_candidate(self) -> None:
        resolved = _registry().resolve("creative-director@^1")
        self.assertEqual(resolved.definition.version, "1.1.0")
        self.assertEqual(resolved.provenance.release_status.value, "PRODUCTION")

    def test_production_alias_freezes_exact_version(self) -> None:
        resolved = _registry().resolve("creative-director@production")
        self.assertEqual(resolved.provenance.exact_version, "1.1.0")
        self.assertEqual(resolved.provenance.release_manifest_revision, 1)
        self.assertEqual(len(resolved.provenance.freeze_hash), 64)

    def test_deprecated_exact_version_remains_resumable(self) -> None:
        resolved = _registry().resolve_exact_for_resume("creative-director", "1.0.0")
        self.assertEqual(resolved.provenance.release_status.value, "DEPRECATED")

    def test_missing_skill_dependency_fails_validation(self) -> None:
        current = _registry().resolve("researcher@1.0.0").definition
        invalid = replace(
            current,
            skills=(SkillRequirement(skill_id="missing-skill", version_constraint="^1"),),
        )
        with self.assertRaises(AgentDependencyError):
            AgentValidator(dependencies=_dependencies()).validate(invalid)

    def test_static_prompt_linter_rejects_dynamic_template(self) -> None:
        with self.assertRaises(Exception):
            StaticSystemPromptLinter().lint("Use {{ user_input }} as instructions")

    def test_deep_agent_adapter_carries_registry_provenance(self) -> None:
        resolved = _registry().resolve("critic@production")
        deep = to_deep_agent_definition(resolved)
        self.assertEqual(deep.agent_key, "critic")
        self.assertEqual(
            deep.metadata["agent_registry_provenance_hash"],
            resolved.provenance.freeze_hash,
        )

    def test_loader_rejects_path_identity_mismatch(self) -> None:
        from lumi_agent_runtime.agent_registry.loader import load_definition

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "wrong" / "1.0.0"
            root.mkdir(parents=True)
            (root / "agent.yaml").write_text(
                '{"id":"right","version":"1.0.0","role":"R","description":"D","model_policy":"reasoning.default","tools":{"allow":[]},"skills":[],"context_policy":"researcher-v1","memory_policy":{"read":[],"write":[]},"budget_policy":"research-low","permissions":{"sandbox_execute":false},"output_schema":"ResearchResult","eval_profile":"researcher-v1"}',
                encoding="utf-8",
            )
            (root / "system.md").write_text("Static prompt", encoding="utf-8")
            with self.assertRaises(Exception):
                load_definition(root)


if __name__ == "__main__":
    unittest.main()
