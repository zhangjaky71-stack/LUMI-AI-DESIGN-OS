from __future__ import annotations

from collections import defaultdict

from lumi_agent_runtime.agent_registry.semver import SemVer, select_highest

from .contracts import (
    ResolvedSkill,
    ResolvedSkillPack,
    SkillDefinition,
    SkillExecutionContext,
    SkillReleaseManifest,
    SkillReleaseRecord,
    SkillReleaseStatus,
)
from .errors import (
    SkillCapabilityError,
    SkillCompatibilityError,
    SkillDependencyConflictError,
    SkillDependencyCycleError,
    SkillNotFoundError,
    SkillPermissionError,
    SkillReleaseError,
    SkillVersionResolutionError,
)


class SkillRegistry:
    def __init__(
        self,
        definitions: tuple[SkillDefinition, ...],
        manifest: SkillReleaseManifest,
    ) -> None:
        self._by_key = {item.identity: item for item in definitions}
        if len(self._by_key) != len(definitions):
            raise SkillReleaseError("duplicate exact Skill version")
        self.manifest = manifest
        self._validate_manifest()
        self._validate_production_dag()

    def definitions(self) -> tuple[SkillDefinition, ...]:
        return tuple(self._by_key[key] for key in sorted(self._by_key))

    def resolve(self, requested_ref: str) -> ResolvedSkill:
        skill_id, selector = _split(requested_ref)
        version, release = self._resolve_version(skill_id, selector)
        definition = self._by_key.get(f"{skill_id}@{version}")
        if definition is None:
            raise SkillNotFoundError(f"Skill not found: {skill_id}@{version}")
        return ResolvedSkill(definition, release.status, requested_ref)

    def resolve_pack(
        self,
        roots: tuple[str, ...],
        context: SkillExecutionContext,
    ) -> ResolvedSkillPack:
        ordered: list[ResolvedSkill] = []
        seen: dict[str, str] = {}
        visiting: list[str] = []

        def visit(resolved: ResolvedSkill) -> None:
            definition = resolved.definition
            existing = seen.get(definition.skill_id)
            if existing is not None:
                if existing != definition.version:
                    raise SkillDependencyConflictError(
                        "conflicting exact Skill versions: "
                        f"{definition.skill_id}@{existing} vs "
                        f"{definition.version}"
                    )
                return
            if definition.identity in visiting:
                cycle = " -> ".join((*visiting, definition.identity))
                raise SkillDependencyCycleError(
                    f"Skill dependency cycle: {cycle}"
                )
            self._validate_context(definition, context)
            visiting.append(definition.identity)
            for dependency in sorted(
                definition.dependencies,
                key=lambda item: item.skill_id,
            ):
                visit(self.resolve(dependency.ref))
            visiting.pop()
            seen[definition.skill_id] = definition.version
            ordered.append(resolved)

        for ref in sorted(set(roots)):
            visit(self.resolve(ref))
        return ResolvedSkillPack(
            tuple(sorted(set(roots))),
            tuple(ordered),
            self.manifest.revision,
        )

    def _validate_context(
        self,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        if context.agent_id not in definition.compatible_agents:
            raise SkillCompatibilityError(
                f"{definition.identity} incompatible with {context.agent_id}"
            )
        missing_tools = {
            item.name for item in definition.required_tools
        } - context.allowed_tools
        if missing_tools:
            raise SkillPermissionError(
                f"Skill requires tools outside Agent scope: {sorted(missing_tools)}"
            )
        missing_permissions = (
            set(definition.permissions) - context.granted_permissions
        )
        if missing_permissions:
            raise SkillPermissionError(
                f"Skill expands Agent permissions: {sorted(missing_permissions)}"
            )
        missing_capabilities = (
            set(definition.required_capabilities)
            - context.available_capabilities
        )
        if missing_capabilities:
            raise SkillCapabilityError(
                f"Skill capabilities unavailable: {sorted(missing_capabilities)}"
            )

    def _resolve_version(
        self,
        skill_id: str,
        selector: str,
    ) -> tuple[str, SkillReleaseRecord]:
        alias = self.manifest.aliases.get(skill_id, {}).get(selector)
        if alias is not None:
            release = self._release(skill_id, alias)
            if (
                selector == "production"
                and release.status != SkillReleaseStatus.PRODUCTION
            ):
                raise SkillReleaseError(
                    "production alias must target PRODUCTION"
                )
            if release.status == SkillReleaseStatus.DISABLED:
                raise SkillReleaseError("Skill alias targets DISABLED")
            return alias, release
        try:
            SemVer.parse(selector)
        except ValueError:
            versions = tuple(
                row.version
                for row in self.manifest.releases
                if row.skill_id == skill_id
                and row.status == SkillReleaseStatus.PRODUCTION
            )
            try:
                version = select_highest(versions, selector)
            except ValueError as exc:
                raise SkillVersionResolutionError(str(exc)) from exc
            if version is None:
                raise SkillVersionResolutionError(
                    f"no production Skill matches: {skill_id}@{selector}"
                )
            return version, self._release(skill_id, version)
        release = self._release(skill_id, selector)
        if release.status in {
            SkillReleaseStatus.DRAFT,
            SkillReleaseStatus.DISABLED,
        }:
            raise SkillReleaseError(
                f"Skill exact version is not runnable: {skill_id}@{selector}"
            )
        return selector, release

    def _release(self, skill_id: str, version: str) -> SkillReleaseRecord:
        row = next(
            (
                item
                for item in self.manifest.releases
                if item.skill_id == skill_id and item.version == version
            ),
            None,
        )
        if row is None:
            raise SkillReleaseError(
                f"Skill release metadata missing: {skill_id}@{version}"
            )
        return row

    def _validate_manifest(self) -> None:
        if (
            self.manifest.schema != "lumi.skill-registry.release.v1"
            or self.manifest.revision < 1
        ):
            raise SkillReleaseError(
                "Skill release manifest schema/revision invalid"
            )
        definitions = set(self._by_key)
        releases = {
            f"{item.skill_id}@{item.version}"
            for item in self.manifest.releases
        }
        if definitions != releases:
            raise SkillReleaseError("Skill release/definition set mismatch")
        production: dict[str, int] = defaultdict(int)
        for row in self.manifest.releases:
            definition = self._by_key[f"{row.skill_id}@{row.version}"]
            if row.eval_profile != definition.eval_profile:
                raise SkillReleaseError(
                    f"release eval profile mismatch: {definition.identity}"
                )
            if row.status == SkillReleaseStatus.PRODUCTION:
                production[row.skill_id] += 1
        if any(count > 1 for count in production.values()):
            raise SkillReleaseError(
                "multiple PRODUCTION versions for one Skill"
            )
        for skill_id, aliases in self.manifest.aliases.items():
            for name, version in aliases.items():
                release = self._release(skill_id, version)
                if release.status == SkillReleaseStatus.DISABLED:
                    raise SkillReleaseError("Skill alias targets DISABLED")
                if (
                    name == "production"
                    and release.status != SkillReleaseStatus.PRODUCTION
                ):
                    raise SkillReleaseError(
                        "Skill production alias targets non-production"
                    )

    def _validate_production_dag(self) -> None:
        visiting: list[str] = []
        visited: set[str] = set()

        def walk(definition: SkillDefinition) -> None:
            if definition.identity in visited:
                return
            if definition.identity in visiting:
                raise SkillDependencyCycleError(
                    "Skill dependency cycle: "
                    + " -> ".join((*visiting, definition.identity))
                )
            visiting.append(definition.identity)
            for dependency in sorted(
                definition.dependencies,
                key=lambda item: item.skill_id,
            ):
                walk(self.resolve(dependency.ref).definition)
            visiting.pop()
            visited.add(definition.identity)

        for row in sorted(
            self.manifest.releases,
            key=lambda item: (item.skill_id, item.version),
        ):
            if row.status == SkillReleaseStatus.PRODUCTION:
                walk(self.resolve(f"{row.skill_id}@{row.version}").definition)


def _split(value: str) -> tuple[str, str]:
    if "@" not in value:
        raise SkillVersionResolutionError(
            "Skill reference must include @selector"
        )
    skill_id, selector = value.rsplit("@", 1)
    if not skill_id or not selector:
        raise SkillVersionResolutionError("Skill reference incomplete")
    return skill_id, selector
