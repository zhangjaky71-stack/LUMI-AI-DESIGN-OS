from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol
from uuid import UUID

from .contracts import CompiledContextBundle, canonical_json
from .errors import ContextBundleIntegrityError, ContextBundleNotFoundError


class ContextBundleStore(Protocol):
    async def put(self, bundle: CompiledContextBundle) -> None: ...

    async def get(self, context_bundle_ref: str) -> CompiledContextBundle: ...


class InMemoryContextBundleStore:
    def __init__(self) -> None:
        self._items: dict[str, CompiledContextBundle] = {}

    async def put(self, bundle: CompiledContextBundle) -> None:
        current = self._items.get(bundle.context_bundle_ref)
        if current is not None and current != bundle:
            raise ContextBundleIntegrityError("CONTEXT_BUNDLE_IMMUTABLE_CONFLICT")
        self._items[bundle.context_bundle_ref] = bundle

    async def get(self, context_bundle_ref: str) -> CompiledContextBundle:
        try:
            return self._items[context_bundle_ref]
        except KeyError as exc:
            raise ContextBundleNotFoundError(
                f"CONTEXT_BUNDLE_NOT_FOUND:{context_bundle_ref}"
            ) from exc


class GitWorkspaceContextBundleStore:
    """Canonical JSON store for a Git-controlled workspace; no Git/network calls."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, bundle: CompiledContextBundle) -> None:
        path = self._path(
            bundle.organization_id, bundle.project_id, bundle.content_hash
        )
        payload = canonical_json(bundle.canonical_record()) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != payload:
                raise ContextBundleIntegrityError("CONTEXT_BUNDLE_IMMUTABLE_CONFLICT")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".context-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    async def get(self, context_bundle_ref: str) -> CompiledContextBundle:
        parts = _parse_ref(context_bundle_ref)
        path = self._path(parts[0], parts[1], parts[2])
        if not path.exists():
            raise ContextBundleNotFoundError(
                f"CONTEXT_BUNDLE_NOT_FOUND:{context_bundle_ref}"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        bundle = CompiledContextBundle(
            context_bundle_ref=data["context_bundle_ref"],
            version=data["version"],
            organization_id=UUID(data["organization_id"]),
            project_id=UUID(data["project_id"]),
            task_id=UUID(data["task_id"]) if data["task_id"] else None,
            brand_id=data["brand_id"],
            user_id=data["user_id"],
            required_memory_scopes=tuple(data["required_memory_scopes"]),
            pinned_constraints=data["pinned_constraints"],
            task_context=data["task_context"],
            source_refs=tuple(data["source_refs"]),
            source_hashes=tuple(data["source_hashes"]),
            content_hash=data["content_hash"],
        )
        if bundle.context_bundle_ref != context_bundle_ref:
            raise ContextBundleIntegrityError("CONTEXT_BUNDLE_REF_TAMPERED")
        return bundle

    def _path(self, organization_id: UUID, project_id: UUID, digest: str) -> Path:
        path = (
            self.root
            / "organizations"
            / str(organization_id)
            / "projects"
            / str(project_id)
            / "context-bundles"
            / f"{digest}.json"
        ).resolve()
        if self.root not in path.parents:
            raise ContextBundleIntegrityError("CONTEXT_BUNDLE_PATH_ESCAPE")
        return path


def _parse_ref(value: str) -> tuple[UUID, UUID, str]:
    prefix = "context-bundle://"
    if not value.startswith(prefix):
        raise ContextBundleIntegrityError("CONTEXT_BUNDLE_REF_INVALID")
    parts = value[len(prefix):].split("/")
    if len(parts) != 3:
        raise ContextBundleIntegrityError("CONTEXT_BUNDLE_REF_INVALID")
    try:
        organization_id = UUID(parts[0])
        project_id = UUID(parts[1])
    except ValueError as exc:
        raise ContextBundleIntegrityError("CONTEXT_BUNDLE_REF_INVALID") from exc
    digest = parts[2]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ContextBundleIntegrityError("CONTEXT_BUNDLE_REF_INVALID")
    return organization_id, project_id, digest
