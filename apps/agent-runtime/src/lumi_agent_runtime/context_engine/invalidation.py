from __future__ import annotations

from dataclasses import dataclass

from .cache import InMemoryContextCache


_INVALIDATING_EVENTS = frozenset(
    {
        "project.summary.updated",
        "project.brief.updated",
        "brand.rule.updated",
        "asset.ready",
        "asset.metadata.updated",
        "artifact.version.created",
        "task.succeeded",
        "task.failed",
        "task.cancelled",
    }
)


@dataclass(frozen=True, slots=True)
class ContextInvalidationEvent:
    event_name: str
    project_id: str
    source_version: str | None = None


class ContextCacheInvalidator:
    def __init__(self, cache: InMemoryContextCache) -> None:
        self.cache = cache

    def handle(self, event: ContextInvalidationEvent) -> int:
        if event.event_name not in _INVALIDATING_EVENTS:
            return 0
        # Project invalidation is conservative and safe. Source-version invalidation is
        # useful for narrow local caches but never substitutes for project invalidation.
        return self.cache.invalidate_project(event.project_id)
