from __future__ import annotations

from lumi_agent_runtime.agent_registry.dependencies import NamedCatalog, VersionedCatalog

from .contracts import SkillDefinition
from .errors import SkillCapabilityError, SkillDefinitionInvalidError

_REQUIRED_HEADINGS = (
    "## When to use",
    "## Required inputs",
    "## Step sequence",
    "## Design heuristics",
    "## Constraints",
    "## Verification checklist",
    "## Failure modes",
    "## Examples",
    "## What not to do",
)
_ALLOWED_EXAMPLE_RIGHTS = {"synthetic", "owned", "licensed"}


class SkillDefinitionValidator:
    def __init__(
        self,
        *,
        tools: VersionedCatalog,
        schemas: NamedCatalog,
        eval_profiles: NamedCatalog,
        known_capabilities: frozenset[str],
    ) -> None:
        self.tools = tools
        self.schemas = schemas
        self.eval_profiles = eval_profiles
        self.known_capabilities = known_capabilities

    def validate(self, definition: SkillDefinition) -> tuple[str, ...]:
        for heading in _REQUIRED_HEADINGS:
            if heading not in definition.skill_markdown:
                raise SkillDefinitionInvalidError(
                    f"{definition.identity} missing required heading: {heading}"
                )
        if definition.metadata.get("example_rights") not in _ALLOWED_EXAMPLE_RIGHTS:
            raise SkillDefinitionInvalidError(
                f"{definition.identity} examples lack approved rights provenance"
            )
        unknown = set(definition.required_capabilities) - self.known_capabilities
        if unknown:
            raise SkillCapabilityError(
                f"unknown Skill capabilities: {sorted(unknown)}"
            )

        evidence: list[str] = []
        for requirement in definition.required_tools:
            tool = self.tools.resolve(
                requirement.name,
                requirement.version_constraint,
            )
            evidence.append(
                f"tool:{requirement.name}@{tool.exact_version}"
            )
        for kind, key, catalog in (
            ("input_schema", definition.input_schema, self.schemas),
            ("output_schema", definition.output_schema, self.schemas),
            ("eval_profile", definition.eval_profile, self.eval_profiles),
        ):
            row = catalog.resolve(key)
            evidence.append(f"{kind}:{row.key}@{row.exact_version}")
        return tuple(evidence)
