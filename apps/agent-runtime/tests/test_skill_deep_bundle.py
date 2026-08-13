from __future__ import annotations

import unittest
from pathlib import Path

from lumi_agent_runtime.skill_registry import (
    DeepAgentsSkillBundle,
    SkillExecutionContext,
    SkillRegistry,
    load_release_manifest,
    load_skills,
)

ROOT = Path(__file__).resolve().parents[3]


class DeepAgentsSkillBundleTests(unittest.TestCase):
    def test_bundle_seeds_only_selected_exact_pack(self) -> None:
        registry = SkillRegistry(
            load_skills(ROOT / "skills"),
            load_release_manifest(ROOT / "skills/registry.json"),
        )
        pack = registry.resolve_pack(
            ("brief-normalization@^1",),
            SkillExecutionContext(
                agent_id="creative-director",
                allowed_tools=frozenset(),
                granted_permissions=frozenset(),
                available_capabilities=frozenset(),
            ),
        )
        bundle = DeepAgentsSkillBundle(pack)
        files = bundle.plain_files()
        self.assertEqual(bundle.sources, ("/skills/",))
        self.assertEqual(
            tuple(files),
            ("/skills/brief-normalization/SKILL.md",),
        )
        self.assertIn("## Verification checklist", next(iter(files.values())))
        self.assertNotIn("poster-design", "\n".join(files))


if __name__ == "__main__":
    unittest.main()
