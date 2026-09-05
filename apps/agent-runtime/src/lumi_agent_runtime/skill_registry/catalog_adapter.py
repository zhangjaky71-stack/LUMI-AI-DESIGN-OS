from __future__ import annotations

from lumi_agent_runtime.agent_registry.dependencies import CatalogEntry

from .registry import SkillRegistry


class Node31SkillCatalog:
    """NODE-30 VersionedCatalog adapter backed by exact NODE-31 Skill releases."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def resolve(self, key: str, selector: str) -> CatalogEntry:
        resolved = self.registry.resolve(f"{key}@{selector}")
        definition = resolved.definition
        return CatalogEntry(
            key=key,
            exact_version=definition.version,
            content_hash=definition.content_hash,
            source_ref=f"NODE-31:{definition.identity}",
        )
