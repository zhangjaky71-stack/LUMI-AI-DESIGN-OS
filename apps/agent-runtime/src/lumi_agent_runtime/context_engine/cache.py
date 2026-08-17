from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from .contracts import ContextManifest


@dataclass(frozen=True, slots=True)
class CacheEntry:
    project_id: str
    source_versions: tuple[str, ...]
    manifest: ContextManifest


class InMemoryContextCache:
    """Process-local derived-view cache; source systems remain authoritative."""

    def __init__(self, *, max_entries: int = 256) -> None:
        if not 1 <= max_entries <= 4096:
            raise ValueError("CONTEXT_CACHE_SIZE_INVALID")
        self.max_entries = max_entries
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()

    def get(
        self,
        key: str,
        *,
        source_versions: tuple[str, ...],
    ) -> ContextManifest | None:
        entry = self._entries.get(key)
        if entry is None or entry.source_versions != source_versions:
            return None
        self._entries.move_to_end(key)
        return entry.manifest

    def put(
        self,
        key: str,
        *,
        project_id: str,
        manifest: ContextManifest,
    ) -> None:
        self._entries[key] = CacheEntry(
            project_id=project_id,
            source_versions=manifest.source_versions,
            manifest=manifest,
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def invalidate_project(self, project_id: str) -> int:
        keys = [
            key
            for key, entry in self._entries.items()
            if entry.project_id == project_id
        ]
        for key in keys:
            self._entries.pop(key, None)
        return len(keys)

    def invalidate_source_version(self, source_version: str) -> int:
        keys = [
            key
            for key, entry in self._entries.items()
            if source_version in entry.source_versions
        ]
        for key in keys:
            self._entries.pop(key, None)
        return len(keys)
