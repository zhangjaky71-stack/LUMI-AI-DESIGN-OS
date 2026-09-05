from __future__ import annotations

from collections import defaultdict

from .contracts import ToolDefinition
from .errors import ToolDisabledError, ToolNotFoundError, ToolVersionError


class ToolRegistry:
    def __init__(self, definitions: tuple[ToolDefinition, ...] = ()) -> None:
        self._by_key: dict[str, ToolDefinition] = {}
        self._versions: dict[str, list[ToolDefinition]] = defaultdict(list)
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ToolDefinition) -> None:
        if definition.key in self._by_key:
            raise ValueError(f"TOOL_DEFINITION_DUPLICATE:{definition.key}")
        self._by_key[definition.key] = definition
        versions = self._versions[definition.name]
        versions.append(definition)
        versions.sort(key=_semver_tuple, reverse=True)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._by_key[key] for key in sorted(self._by_key))

    def resolve(self, name: str, version_constraint: str) -> ToolDefinition:
        candidates = self._versions.get(name)
        if not candidates:
            raise ToolNotFoundError(f"tool is not registered: {name}")
        definition: ToolDefinition | None = None
        if version_constraint.endswith(".x"):
            major_text = version_constraint[:-2]
            if not major_text.isdigit():
                raise ToolVersionError(f"invalid tool major constraint: {version_constraint}")
            major = int(major_text)
            definition = next((item for item in candidates if item.major == major), None)
        else:
            definition = self._by_key.get(f"{name}@{version_constraint}")
        if definition is None:
            raise ToolVersionError(f"tool version not found: {name}@{version_constraint}")
        if not definition.enabled:
            raise ToolDisabledError(f"tool is disabled: {definition.key}")
        return definition


def _semver_tuple(definition: ToolDefinition) -> tuple[int, int, int]:
    major, minor, patch = definition.version.split(".")
    return int(major), int(minor), int(patch)
