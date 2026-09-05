from __future__ import annotations

from .contracts import DeepAgentDefinition
from .errors import (
    DeepAgentDisabledError,
    DeepAgentNotFoundError,
    DeepAgentVersionConflictError,
)


class DeepAgentRegistry:
    def __init__(self, definitions: tuple[DeepAgentDefinition, ...] = ()) -> None:
        self._definitions: dict[tuple[str, str], DeepAgentDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: DeepAgentDefinition) -> None:
        key = (definition.agent_key, definition.runtime_version)
        existing = self._definitions.get(key)
        if existing is not None:
            if existing.content_hash != definition.content_hash:
                raise DeepAgentVersionConflictError(
                    f"same Deep Agent version has different content: {definition.identity}"
                )
            return
        self._definitions[key] = definition

    def resolve(
        self,
        agent_key: str,
        runtime_version: str,
        *,
        require_enabled: bool = True,
    ) -> DeepAgentDefinition:
        try:
            definition = self._definitions[(agent_key, runtime_version)]
        except KeyError as exc:
            raise DeepAgentNotFoundError(
                f"Deep Agent not found: {agent_key}@{runtime_version}"
            ) from exc
        if require_enabled and not definition.enabled:
            raise DeepAgentDisabledError(f"Deep Agent disabled: {definition.identity}")
        return definition

    def definitions(self) -> tuple[DeepAgentDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))
