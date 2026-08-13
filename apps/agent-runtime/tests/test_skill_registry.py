from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lumi_agent_runtime.agent_registry.requirements import SkillRequirement
from lumi_agent_runtime.skill_registry import (
    SkillCapabilityError,
    SkillDefinition,
    SkillDependencyCycleError,
    SkillExecutionContext,
    SkillPermissionError,
    SkillRegistry,
    SkillReleaseManifest,
    SkillReleaseRecord,
    SkillReleaseStatus,
    SkillSelectionContext,
    SkillSelector,
    load_release_manifest,
    load_skill,
    load_skills,
)

ROOT = Path(__file__).resolve().parents[3]


def registry() -> SkillRegistry:
    return SkillRegistry(
        load_skills(ROOT / "skills"),
        load_release_manifest(ROOT / "skills/registry.json"),
    )


def creative_context(*, capabilities=()) -> SkillExecutionContext:
    return SkillExecutionContext(
        agent_id="creative-director",
        allowed_tools=frozenset(
            {"web.search", "web.fetch", "asset.read", "artifact.query"}
        ),
        granted_permissions=frozenset(),
        available_capabilities=frozenset(capabilities),
    )


class SkillRegistryTests(unittest.TestCase):
    def test_p0_catalog_has_14_ids_and_15_exact_versions(self) -> None:
        definitions = registry().definitions()
        self.assertEqual(len(definitions), 15)
        self.assertEqual(len({item.skill_id for item in definitions}), 14)

    def test_range_resolves_production_and_exact_old_version(self) -> None:
        resolved = registry().resolve("creative-direction@^1")
        self.assertEqual(resolved.definition.version, "1.1.0")
        self.assertEqual(resolved.release_status, SkillReleaseStatus.PRODUCTION)
        old = registry().resolve("creative-direction@1.0.0")
        self.assertEqual(old.release_status, SkillReleaseStatus.DEPRECATED)

    def test_poster_pack_is_dependency_first_and_minimal(self) -> None:
        pack = registry().resolve_pack(
            ("poster-design@^1",),
            creative_context(),
        )
        identities = [item.definition.skill_id for item in pack.skills]
        self.assertEqual(
            identities,
            [
                "brief-normalization",
                "web-research",
                "brand-strategy",
                "creative-direction",
                "typography",
                "layout",
                "poster-design",
            ],
        )
        self.assertNotIn("image-edit", identities)
        self.assertNotIn("product-render", identities)
        self.assertEqual(len(pack.freeze_hash), 64)

    def test_selector_loads_one_primary_skill_plus_dag(self) -> None:
        pack = SkillSelector(registry()).select(
            SkillSelectionContext(
                task_type="poster-design",
                execution=creative_context(),
            )
        )
        self.assertEqual(pack.roots, ("poster-design@1.0.0",))
        self.assertEqual(pack.skills[-1].definition.skill_id, "poster-design")

    def test_missing_tool_scope_is_rejected(self) -> None:
        context = SkillExecutionContext(
            agent_id="creative-director",
            allowed_tools=frozenset({"asset.read", "artifact.query"}),
            granted_permissions=frozenset(),
            available_capabilities=frozenset(),
        )
        with self.assertRaises(SkillPermissionError):
            registry().resolve_pack(("moodboard@^1",), context)

    def test_missing_model_capability_is_rejected(self) -> None:
        with self.assertRaises(SkillCapabilityError):
            registry().resolve_pack(
                ("image-generation@^1",),
                creative_context(),
            )
        pack = registry().resolve_pack(
            ("image-generation@^1",),
            creative_context(capabilities=("image.generate",)),
        )
        self.assertEqual(pack.skills[-1].definition.skill_id, "image-generation")

    def test_dependency_cycle_is_rejected(self) -> None:
        a = SkillDefinition(
            skill_id="a",
            version="1.0.0",
            summary="A",
            compatible_agents=("critic",),
            required_tools=(),
            required_capabilities=(),
            input_schema="GenericTaskInput",
            output_schema="PlanOutput",
            permissions=(),
            dependencies=(SkillRequirement("b", "^1"),),
            eval_profile="a-v1",
            task_types=(),
            skill_markdown="---\nname: a\ndescription: A\n---\nbody",
        )
        b = SkillDefinition(
            skill_id="b",
            version="1.0.0",
            summary="B",
            compatible_agents=("critic",),
            required_tools=(),
            required_capabilities=(),
            input_schema="GenericTaskInput",
            output_schema="PlanOutput",
            permissions=(),
            dependencies=(SkillRequirement("a", "^1"),),
            eval_profile="b-v1",
            task_types=(),
            skill_markdown="---\nname: b\ndescription: B\n---\nbody",
        )
        manifest = SkillReleaseManifest(
            schema="lumi.skill-registry.release.v1",
            revision=1,
            releases=(
                SkillReleaseRecord(
                    "a", "1.0.0", SkillReleaseStatus.PRODUCTION,
                    "a-v1", "passed", "eval://a",
                ),
                SkillReleaseRecord(
                    "b", "1.0.0", SkillReleaseStatus.PRODUCTION,
                    "b-v1", "passed", "eval://b",
                ),
            ),
            aliases={
                "a": {"production": "1.0.0"},
                "b": {"production": "1.0.0"},
            },
        )
        with self.assertRaises(SkillDependencyCycleError):
            SkillRegistry((a, b), manifest)

    def test_frontmatter_mismatch_fails_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            version_dir = Path(tmp) / "expected" / "1.0.0"
            version_dir.mkdir(parents=True)
            (version_dir / "skill.yaml").write_text(
                '{"id":"expected","version":"1.0.0","summary":"Expected summary",'
                '"compatible_agents":["critic"],"required_tools":[],"required_capabilities":[],"input_schema":"GenericTaskInput","output_schema":"PlanOutput","permissions":[],"dependencies":[],"eval_profile":"expected-v1","task_types":[],"metadata":{}}',
                encoding="utf-8",
            )
            (version_dir / "SKILL.md").write_text(
                "---\nname: wrong\ndescription: Expected summary\n---\nbody",
                encoding="utf-8",
            )
            with self.assertRaises(Exception):
                load_skill(version_dir)


if __name__ == "__main__":
    unittest.main()
