from __future__ import annotations

from .contracts import GraphDefinition
from .errors import GraphDisabledError, GraphNotFoundError, GraphVersionConflictError


class GraphRegistry:
    """Immutable-version registry for code-deployed LangGraph definitions."""

    def __init__(self, definitions: tuple[GraphDefinition, ...] = ()) -> None:
        self._definitions: dict[tuple[str, str], GraphDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: GraphDefinition) -> None:
        key = (definition.graph_key, definition.graph_version)
        existing = self._definitions.get(key)
        if existing is not None:
            if existing.content_hash != definition.content_hash:
                raise GraphVersionConflictError(
                    f"same graph version has different content: {definition.identity}"
                )
            return
        self._definitions[key] = definition

    def resolve(
        self,
        graph_key: str,
        graph_version: str,
        *,
        agent_config_version: str | None = None,
        require_enabled: bool = True,
    ) -> GraphDefinition:
        try:
            definition = self._definitions[(graph_key, graph_version)]
        except KeyError as exc:
            raise GraphNotFoundError(f"graph not found: {graph_key}@{graph_version}") from exc
        if require_enabled and not definition.enabled:
            raise GraphDisabledError(f"graph disabled: {definition.identity}")
        if (
            agent_config_version is not None
            and definition.agent_config_version != agent_config_version
        ):
            raise GraphVersionConflictError(
                "agent config version does not match immutable graph definition"
            )
        return definition

    def definitions(self) -> tuple[GraphDefinition, ...]:
        return tuple(
            self._definitions[key]
            for key in sorted(self._definitions)
        )
