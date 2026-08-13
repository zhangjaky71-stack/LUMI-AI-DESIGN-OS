from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .definition import AgentDefinition
from .errors import AgentDependencyError
from .provenance import ResolvedDependency
from .semver import select_highest


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    key: str
    exact_version: str
    content_hash: str | None = None
    source_ref: str | None = None


class NamedCatalog(Protocol):
    def resolve(self, key: str) -> CatalogEntry: ...


class VersionedCatalog(Protocol):
    def resolve(self, key: str, selector: str) -> CatalogEntry: ...


class StaticNamedCatalog:
    def __init__(self, rows: dict[str, CatalogEntry]) -> None:
        self._rows = dict(rows)

    def resolve(self, key: str) -> CatalogEntry:
        try:
            return self._rows[key]
        except KeyError as exc:
            raise AgentDependencyError(f"dependency not found: {key}") from exc


class StaticVersionedCatalog:
    def __init__(self, rows: dict[str, tuple[CatalogEntry, ...]]) -> None:
        self._rows = dict(rows)

    def resolve(self, key: str, selector: str) -> CatalogEntry:
        candidates = self._rows.get(key, ())
        selected = select_highest(tuple(item.exact_version for item in candidates), selector)
        if selected is None:
            raise AgentDependencyError(f"dependency version not found: {key}@{selector}")
        return next(item for item in candidates if item.exact_version == selected)


class Node23ModelPolicyCatalog:
    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def resolve(self, key: str) -> CatalogEntry:
        snapshot = self.registry.snapshot()
        profile = next((item for item in snapshot.routing_profiles if item.profile == key), None)
        if profile is None:
            raise AgentDependencyError(f"model policy not found in NODE-23 Registry: {key}")
        return CatalogEntry(
            key=key,
            exact_version=f"registry-{snapshot.registry_version}",
            content_hash=snapshot.content_hash,
            source_ref=f"{snapshot.source_ref}#routing-profile:{key}",
        )


class Node25ToolCatalog:
    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def resolve(self, key: str, selector: str) -> CatalogEntry:
        try:
            definition = self.registry.resolve(key, selector)
        except Exception as exc:
            raise AgentDependencyError(f"tool dependency invalid: {key}@{selector}") from exc
        payload = {
            "name": definition.name,
            "version": definition.version,
            "risk": getattr(definition.risk, "value", str(definition.risk)),
            "runtime": getattr(definition.runtime, "value", str(definition.runtime)),
            "permissions": sorted(definition.permissions),
            "input_schema": definition.input_schema,
            "output_schema": definition.output_schema,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return CatalogEntry(
            key=key,
            exact_version=definition.version,
            content_hash=digest,
            source_ref=f"NODE-25:{definition.name}@{definition.version}",
        )


class DependencyResolver:
    def __init__(
        self,
        *,
        model_policies: NamedCatalog,
        tools: VersionedCatalog,
        skills: VersionedCatalog,
        context_policies: NamedCatalog,
        budget_policies: NamedCatalog,
        output_schemas: NamedCatalog,
        eval_profiles: NamedCatalog,
    ) -> None:
        self.model_policies = model_policies
        self.tools = tools
        self.skills = skills
        self.context_policies = context_policies
        self.budget_policies = budget_policies
        self.output_schemas = output_schemas
        self.eval_profiles = eval_profiles

    def resolve(self, definition: AgentDefinition) -> tuple[ResolvedDependency, ...]:
        rows: list[ResolvedDependency] = []
        rows.append(_resolved("model_policy", definition.model_policy, definition.model_policy, self.model_policies.resolve(definition.model_policy)))
        for item in definition.tools:
            rows.append(_resolved("tool", item.name, item.version_constraint, self.tools.resolve(item.name, item.version_constraint)))
        for item in definition.skills:
            rows.append(_resolved("skill", item.skill_id, item.version_constraint, self.skills.resolve(item.skill_id, item.version_constraint)))
        rows.append(_resolved("context_policy", definition.context_policy, definition.context_policy, self.context_policies.resolve(definition.context_policy)))
        memory_payload = json.dumps(
            {"read": sorted(definition.memory_policy.read), "write": sorted(definition.memory_policy.write)},
            sort_keys=True,
            separators=(",", ":"),
        )
        rows.append(
            ResolvedDependency(
                kind="memory_policy",
                key="inline",
                requested="inline",
                exact_version="inline-v1",
                content_hash=hashlib.sha256(memory_payload.encode()).hexdigest(),
                source_ref=f"{definition.identity}#memory_policy",
            )
        )
        rows.append(_resolved("budget_policy", definition.budget_policy, definition.budget_policy, self.budget_policies.resolve(definition.budget_policy)))
        rows.append(_resolved("output_schema", definition.output_schema, definition.output_schema, self.output_schemas.resolve(definition.output_schema)))
        rows.append(_resolved("eval_profile", definition.eval_profile, definition.eval_profile, self.eval_profiles.resolve(definition.eval_profile)))
        return tuple(rows)


def load_bootstrap_catalog(path: Path, section: str) -> StaticNamedCatalog | StaticVersionedCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get(section)
    if not isinstance(raw, dict):
        raise AgentDependencyError(f"bootstrap dependency section missing: {section}")
    if section == "skills":
        rows: dict[str, tuple[CatalogEntry, ...]] = {}
        for key, versions in raw.items():
            if not isinstance(versions, list):
                raise AgentDependencyError(f"bootstrap skill versions invalid: {key}")
            rows[str(key)] = tuple(_entry(str(key), item) for item in versions)
        return StaticVersionedCatalog(rows)
    return StaticNamedCatalog({str(key): _entry(str(key), value) for key, value in raw.items()})


def _entry(key: str, raw: Any) -> CatalogEntry:
    if not isinstance(raw, dict):
        raise AgentDependencyError(f"bootstrap dependency entry invalid: {key}")
    version = raw.get("version")
    if not isinstance(version, str) or not version:
        raise AgentDependencyError(f"bootstrap dependency version invalid: {key}")
    return CatalogEntry(
        key=key,
        exact_version=version,
        content_hash=raw.get("content_hash") if isinstance(raw.get("content_hash"), str) else None,
        source_ref=raw.get("source_ref") if isinstance(raw.get("source_ref"), str) else None,
    )


def _resolved(kind: str, key: str, requested: str, entry: CatalogEntry) -> ResolvedDependency:
    return ResolvedDependency(
        kind=kind,
        key=key,
        requested=requested,
        exact_version=entry.exact_version,
        content_hash=entry.content_hash,
        source_ref=entry.source_ref,
    )
