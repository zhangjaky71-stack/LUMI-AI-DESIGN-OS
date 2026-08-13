from __future__ import annotations

from collections import defaultdict

from .definition import AgentDefinition
from .errors import (
    AgentDefinitionNotFoundError,
    AgentReleaseError,
    AgentVersionConflictError,
    AgentVersionResolutionError,
)
from .provenance import AgentProvenance, ResolvedAgent
from .release_types import AgentReleaseManifest, AgentReleaseRecord, AgentReleaseStatus
from .semver import SemVer, select_highest
from .validator import AgentValidator


class AgentRegistry:
    def __init__(
        self,
        definitions: tuple[AgentDefinition, ...],
        release_manifest: AgentReleaseManifest,
        validator: AgentValidator,
    ) -> None:
        self._by_key: dict[str, AgentDefinition] = {}
        self._versions: dict[str, list[str]] = defaultdict(list)
        self.release_manifest = release_manifest
        self.validator = validator
        for definition in definitions:
            key = definition.identity
            existing = self._by_key.get(key)
            if existing is not None and existing.content_hash != definition.content_hash:
                raise AgentVersionConflictError(f"same Agent version has different content: {key}")
            self._by_key[key] = definition
            self._versions[definition.agent_id].append(definition.version)
        self._validate_release_manifest()

    def definitions(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._by_key[key] for key in sorted(self._by_key))

    def resolve(self, requested_ref: str) -> ResolvedAgent:
        agent_id, selector = _split_ref(requested_ref)
        exact_version, release = self._resolve_version(agent_id, selector)
        definition = self._by_key.get(f"{agent_id}@{exact_version}")
        if definition is None:
            raise AgentDefinitionNotFoundError(f"Agent definition not found: {agent_id}@{exact_version}")
        dependencies = self.validator.validate(definition)
        provenance = AgentProvenance(
            requested_ref=requested_ref,
            agent_id=definition.agent_id,
            exact_version=definition.version,
            release_status=release.status,
            definition_hash=definition.content_hash,
            system_prompt_hash=definition.system_prompt_hash,
            release_manifest_revision=self.release_manifest.revision,
            dependencies=dependencies,
        )
        return ResolvedAgent(definition=definition, provenance=provenance)

    def resolve_exact_for_resume(self, agent_id: str, exact_version: str) -> ResolvedAgent:
        SemVer.parse(exact_version)
        return self.resolve(f"{agent_id}@{exact_version}")

    def _resolve_version(self, agent_id: str, selector: str) -> tuple[str, AgentReleaseRecord]:
        aliases = self.release_manifest.aliases.get(agent_id, {})
        if selector in aliases:
            version = aliases[selector]
            release = self._release(agent_id, version)
            if release.status == AgentReleaseStatus.DISABLED:
                raise AgentReleaseError(f"Agent alias targets disabled release: {agent_id}@{version}")
            return version, release
        try:
            SemVer.parse(selector)
        except ValueError:
            return self._resolve_range(agent_id, selector)
        release = self._release(agent_id, selector)
        if release.status in {AgentReleaseStatus.DISABLED, AgentReleaseStatus.DRAFT}:
            raise AgentReleaseError(f"Agent exact release is not runnable: {agent_id}@{selector}:{release.status.value}")
        return selector, release

    def _resolve_range(self, agent_id: str, selector: str) -> tuple[str, AgentReleaseRecord]:
        production_versions = tuple(
            row.version
            for row in self.release_manifest.releases
            if row.agent_id == agent_id and row.status == AgentReleaseStatus.PRODUCTION
        )
        try:
            version = select_highest(production_versions, selector)
        except ValueError as exc:
            raise AgentVersionResolutionError(str(exc)) from exc
        if version is None:
            raise AgentVersionResolutionError(f"no production Agent matches: {agent_id}@{selector}")
        return version, self._release(agent_id, version)

    def _release(self, agent_id: str, version: str) -> AgentReleaseRecord:
        row = next(
            (item for item in self.release_manifest.releases if item.agent_id == agent_id and item.version == version),
            None,
        )
        if row is None:
            raise AgentReleaseError(f"Agent release metadata missing: {agent_id}@{version}")
        return row

    def _validate_release_manifest(self) -> None:
        definition_keys = set(self._by_key)
        release_keys = {f"{row.agent_id}@{row.version}" for row in self.release_manifest.releases}
        if definition_keys != release_keys:
            missing_release = sorted(definition_keys - release_keys)
            missing_definition = sorted(release_keys - definition_keys)
            raise AgentReleaseError(
                f"release/definition mismatch: missing_release={missing_release}, missing_definition={missing_definition}"
            )
        for agent_id, aliases in self.release_manifest.aliases.items():
            for alias, version in aliases.items():
                release = self._release(agent_id, version)
                if release.status == AgentReleaseStatus.DISABLED:
                    raise AgentReleaseError(f"alias {agent_id}@{alias} targets DISABLED version")
        production_counts: dict[str, int] = defaultdict(int)
        for release in self.release_manifest.releases:
            if release.status == AgentReleaseStatus.PRODUCTION:
                production_counts[release.agent_id] += 1
        for agent_id, count in production_counts.items():
            if count > 1:
                raise AgentReleaseError(f"multiple PRODUCTION versions for {agent_id}")


def _split_ref(value: str) -> tuple[str, str]:
    if "@" not in value:
        raise AgentVersionResolutionError("Agent reference must include @selector")
    agent_id, selector = value.rsplit("@", 1)
    if not agent_id or not selector:
        raise AgentVersionResolutionError("Agent reference is incomplete")
    return agent_id, selector
