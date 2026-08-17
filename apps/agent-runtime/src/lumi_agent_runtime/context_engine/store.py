from __future__ import annotations

from typing import Protocol

from .contracts import ContextManifest
from .errors import ContextIntegrityError


class RuntimeContextManifestStore(Protocol):
    async def store(self, manifest: ContextManifest) -> str: ...

    async def get(self, runtime_context_ref: str) -> ContextManifest: ...


class InMemoryRuntimeContextManifestStore:
    def __init__(self) -> None:
        self._items: dict[str, ContextManifest] = {}

    async def store(self, manifest: ContextManifest) -> str:
        ref = manifest.runtime_context_ref
        existing = self._items.get(ref)
        if existing is not None and existing.freeze_hash != manifest.freeze_hash:
            raise ContextIntegrityError("CONTEXT_MANIFEST_IMMUTABILITY_CONFLICT")
        self._items[ref] = manifest
        return ref

    async def get(self, runtime_context_ref: str) -> ContextManifest:
        try:
            return self._items[runtime_context_ref]
        except KeyError as exc:
            raise ContextIntegrityError("CONTEXT_MANIFEST_NOT_FOUND") from exc
