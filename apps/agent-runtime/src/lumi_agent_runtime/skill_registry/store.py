from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Protocol

from .contracts import PublishedSkill, SkillScope, published_from_dict, published_to_dict, parse_skill_ref
from .errors import SkillRegistryConflictError


class SkillRegistryStore(Protocol):
    async def get_release(
        self,
        *,
        scope: SkillScope,
        skill_id: str,
        exact_version: str,
    ) -> PublishedSkill | None: ...

    async def put_release(self, release: PublishedSkill) -> PublishedSkill: ...

    async def list_releases(
        self,
        *,
        scope: SkillScope,
        skill_id: str,
    ) -> tuple[PublishedSkill, ...]: ...


class InMemorySkillRegistryStore:
    def __init__(self) -> None:
        self._releases: dict[tuple[str, str, str], PublishedSkill] = {}
        self._lock = asyncio.Lock()

    async def get_release(
        self,
        *,
        scope: SkillScope,
        skill_id: str,
        exact_version: str,
    ) -> PublishedSkill | None:
        return self._releases.get((scope.key, skill_id, exact_version))

    async def put_release(self, release: PublishedSkill) -> PublishedSkill:
        key = (release.scope.key, release.manifest.skill_id, release.manifest.version)
        async with self._lock:
            existing = self._releases.get(key)
            if existing is not None:
                if existing.content_hash != release.content_hash:
                    raise SkillRegistryConflictError(
                        "SKILL_REGISTRY_IMMUTABLE_VERSION_CONFLICT"
                    )
                return existing
            self._releases[key] = release
            return release

    async def list_releases(
        self,
        *,
        scope: SkillScope,
        skill_id: str,
    ) -> tuple[PublishedSkill, ...]:
        values = [
            release
            for (scope_key, stored_id, _), release in self._releases.items()
            if scope_key == scope.key and stored_id == skill_id
        ]
        return tuple(sorted(values, key=lambda item: item.manifest.version))


class GitWorkspaceSkillRegistryStore:
    """Canonical JSON store intended for a Git-controlled config workspace."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._lock = asyncio.Lock()

    async def get_release(
        self,
        *,
        scope: SkillScope,
        skill_id: str,
        exact_version: str,
    ) -> PublishedSkill | None:
        value = self._read_json(self._release_path(scope, skill_id, exact_version))
        return published_from_dict(value) if value is not None else None

    async def put_release(self, release: PublishedSkill) -> PublishedSkill:
        path = self._release_path(
            release.scope,
            release.manifest.skill_id,
            release.manifest.version,
        )
        async with self._lock:
            existing_value = self._read_json(path)
            if existing_value is not None:
                existing = published_from_dict(existing_value)
                if existing.content_hash != release.content_hash:
                    raise SkillRegistryConflictError(
                        "SKILL_REGISTRY_IMMUTABLE_VERSION_CONFLICT"
                    )
                return existing
            self._atomic_write(path, published_to_dict(release))
            return release

    async def list_releases(
        self,
        *,
        scope: SkillScope,
        skill_id: str,
    ) -> tuple[PublishedSkill, ...]:
        directory = self._skill_path(scope, skill_id) / "versions"
        if not directory.exists():
            return ()
        values = []
        for path in sorted(directory.glob("*.json")):
            value = self._read_json(path)
            if value is not None:
                values.append(published_from_dict(value))
        return tuple(values)

    def _scope_path(self, scope: SkillScope) -> Path:
        if scope.project_id is not None:
            return (
                self._root
                / "scopes"
                / "organizations"
                / str(scope.organization_id)
                / "projects"
                / str(scope.project_id)
            )
        if scope.organization_id is not None:
            return (
                self._root
                / "scopes"
                / "organizations"
                / str(scope.organization_id)
                / "shared"
            )
        return self._root / "scopes" / "global"

    def _skill_path(self, scope: SkillScope, skill_id: str) -> Path:
        parse_skill_ref(f"{skill_id}@1")
        return self._scope_path(scope) / "skills" / skill_id

    def _release_path(
        self,
        scope: SkillScope,
        skill_id: str,
        exact_version: str,
    ) -> Path:
        parse_skill_ref(f"{skill_id}@{exact_version}")
        return self._skill_path(scope, skill_id) / "versions" / f"{exact_version}.json"

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
