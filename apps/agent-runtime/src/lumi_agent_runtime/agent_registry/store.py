from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Protocol

from .contracts import (
    AgentAlias,
    AgentScope,
    PublishedAgent,
    alias_from_dict,
    alias_to_dict,
    published_from_dict,
    published_to_dict,
    parse_agent_ref,
    validate_alias,
)
from .errors import AgentRegistryConflictError


class AgentRegistryStore(Protocol):
    async def get_release(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        exact_version: str,
    ) -> PublishedAgent | None: ...

    async def put_release(
        self,
        release: PublishedAgent,
    ) -> PublishedAgent: ...

    async def list_releases(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
    ) -> tuple[PublishedAgent, ...]: ...

    async def get_alias(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        alias: str,
    ) -> AgentAlias | None: ...

    async def put_alias(
        self,
        value: AgentAlias,
    ) -> AgentAlias: ...


class InMemoryAgentRegistryStore:
    def __init__(self) -> None:
        self._releases: dict[
            tuple[str, str, str],
            PublishedAgent,
        ] = {}
        self._aliases: dict[tuple[str, str, str], AgentAlias] = {}
        self._lock = asyncio.Lock()

    async def get_release(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        exact_version: str,
    ) -> PublishedAgent | None:
        return self._releases.get((scope.key, agent_id, exact_version))

    async def put_release(
        self,
        release: PublishedAgent,
    ) -> PublishedAgent:
        key = (
            release.scope.key,
            release.manifest.agent_id,
            release.manifest.version,
        )
        async with self._lock:
            existing = self._releases.get(key)
            if existing is not None:
                if existing.content_hash != release.content_hash:
                    raise AgentRegistryConflictError(
                        "AGENT_REGISTRY_IMMUTABLE_VERSION_CONFLICT"
                    )
                return existing
            self._releases[key] = release
            return release

    async def list_releases(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
    ) -> tuple[PublishedAgent, ...]:
        values = [
            release
            for (scope_key, stored_id, _), release in self._releases.items()
            if scope_key == scope.key and stored_id == agent_id
        ]
        return tuple(
            sorted(values, key=lambda item: item.manifest.version)
        )

    async def get_alias(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        alias: str,
    ) -> AgentAlias | None:
        return self._aliases.get((scope.key, agent_id, alias))

    async def put_alias(
        self,
        value: AgentAlias,
    ) -> AgentAlias:
        key = (value.scope.key, value.agent_id, value.alias)
        async with self._lock:
            existing = self._aliases.get(key)
            if existing is not None and value.revision != existing.revision + 1:
                raise AgentRegistryConflictError(
                    "AGENT_REGISTRY_ALIAS_REVISION_CONFLICT"
                )
            if existing is None and value.revision != 1:
                raise AgentRegistryConflictError(
                    "AGENT_REGISTRY_ALIAS_REVISION_CONFLICT"
                )
            self._aliases[key] = value
            return value


class GitWorkspaceAgentRegistryStore:
    """Canonical JSON store intended to live inside a Git-controlled workspace.

    The adapter never executes git or handles provider credentials. CI/CD or a
    control-plane publisher is responsible for committing/promoting the files.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._lock = asyncio.Lock()

    async def get_release(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        exact_version: str,
    ) -> PublishedAgent | None:
        path = self._release_path(scope, agent_id, exact_version)
        value = self._read_json(path)
        return published_from_dict(value) if value is not None else None

    async def put_release(
        self,
        release: PublishedAgent,
    ) -> PublishedAgent:
        path = self._release_path(
            release.scope,
            release.manifest.agent_id,
            release.manifest.version,
        )
        async with self._lock:
            existing_value = self._read_json(path)
            if existing_value is not None:
                existing = published_from_dict(existing_value)
                if existing.content_hash != release.content_hash:
                    raise AgentRegistryConflictError(
                        "AGENT_REGISTRY_IMMUTABLE_VERSION_CONFLICT"
                    )
                return existing
            self._atomic_write(path, published_to_dict(release))
            return release

    async def list_releases(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
    ) -> tuple[PublishedAgent, ...]:
        directory = self._agent_path(scope, agent_id) / "versions"
        if not directory.exists():
            return ()
        values = []
        for path in sorted(directory.glob("*.json")):
            value = self._read_json(path)
            if value is not None:
                values.append(published_from_dict(value))
        return tuple(values)

    async def get_alias(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        alias: str,
    ) -> AgentAlias | None:
        validate_alias(alias)
        path = self._agent_path(scope, agent_id) / "aliases" / f"{alias}.json"
        value = self._read_json(path)
        return alias_from_dict(value) if value is not None else None

    async def put_alias(
        self,
        value: AgentAlias,
    ) -> AgentAlias:
        path = (
            self._agent_path(value.scope, value.agent_id)
            / "aliases"
            / f"{value.alias}.json"
        )
        async with self._lock:
            existing_value = self._read_json(path)
            if existing_value is None:
                if value.revision != 1:
                    raise AgentRegistryConflictError(
                        "AGENT_REGISTRY_ALIAS_REVISION_CONFLICT"
                    )
            else:
                existing = alias_from_dict(existing_value)
                if value.revision != existing.revision + 1:
                    raise AgentRegistryConflictError(
                        "AGENT_REGISTRY_ALIAS_REVISION_CONFLICT"
                    )
            self._atomic_write(path, alias_to_dict(value))
            return value

    def _scope_path(self, scope: AgentScope) -> Path:
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

    def _agent_path(self, scope: AgentScope, agent_id: str) -> Path:
        parse_agent_ref(f"{agent_id}@1")
        return self._scope_path(scope) / "agents" / agent_id

    def _release_path(
        self,
        scope: AgentScope,
        agent_id: str,
        exact_version: str,
    ) -> Path:
        parse_agent_ref(f"{agent_id}@{exact_version}")
        return (
            self._agent_path(scope, agent_id)
            / "versions"
            / f"{exact_version}.json"
        )

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
