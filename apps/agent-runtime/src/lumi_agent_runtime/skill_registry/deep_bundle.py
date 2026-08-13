from __future__ import annotations

from importlib import import_module
from typing import Any

from .contracts import ResolvedSkillPack
from .errors import SkillDefinitionInvalidError


class DeepAgentsSkillBundle:
    """Seed only the selected exact Skill DAG into Deep Agents virtual files."""

    def __init__(self, pack: ResolvedSkillPack) -> None:
        self.pack = pack

    @property
    def sources(self) -> tuple[str, ...]:
        return ("/skills/",)

    def plain_files(self) -> dict[str, str]:
        files: dict[str, str] = {}
        for resolved in self.pack.skills:
            definition = resolved.definition
            base = f"/skills/{definition.skill_id}"
            files[f"{base}/SKILL.md"] = definition.skill_markdown
            for relative, content in sorted(definition.resources.items()):
                path = f"{base}/{relative}"
                if path in files:
                    raise SkillDefinitionInvalidError(
                        f"Skill bundle path collision: {path}"
                    )
                files[path] = content
        return files

    def deep_agents_files(self) -> dict[str, Any]:
        try:
            helper = getattr(
                import_module("deepagents.backends.utils"),
                "create_file_data",
            )
        except (ImportError, AttributeError) as exc:
            raise SkillDefinitionInvalidError(
                "current Deep Agents create_file_data is unavailable"
            ) from exc
        return {
            path: helper(content)
            for path, content in self.plain_files().items()
        }


def inject_skill_files(
    input_state: dict[str, Any],
    bundle: DeepAgentsSkillBundle,
) -> dict[str, Any]:
    result = dict(input_state)
    existing = result.get("files", {})
    if not isinstance(existing, dict):
        raise SkillDefinitionInvalidError(
            "Deep Agents input files must be an object"
        )
    merged = dict(existing)
    for path, value in bundle.deep_agents_files().items():
        if path in merged:
            raise SkillDefinitionInvalidError(
                f"Skill seed would overwrite existing file: {path}"
            )
        merged[path] = value
    result["files"] = merged
    return result
