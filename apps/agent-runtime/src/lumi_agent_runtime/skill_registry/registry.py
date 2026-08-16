from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    MaterializedSkill,
    ResolvedAgentConfig,
    stable_hash,
)

from .contracts import (
    PublishedSkill,
    SkillEvaluationEvidence,
    SkillManifest,
    SkillScope,
    manifest_to_dict,
    parse_skill_ref,
)
from .errors import (
    SkillRegistryConflictError,
    SkillRegistryDependencyError,
    SkillRegistryMaterializationError,
    SkillRegistryNotFoundError,
    SkillRegistryPermissionError,
    SkillRegistryPublicationError,
)
from .evaluation import SkillEvaluationGate, ThresholdSkillEvaluationGate
from .materializer import MaterializationFile, SkillPackageSink, dependency_index
from .store import SkillRegistryStore

Clock = Callable[[], str]


class SkillRegistry:
    def __init__(
        self,
        store: SkillRegistryStore,
        *,
        evaluator: SkillEvaluationGate | None = None,
        sink: SkillPackageSink | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._evaluator = evaluator or ThresholdSkillEvaluationGate()
        self._sink = sink
        self._clock = clock or _utc_now

    async def publication_subject_hash(
        self,
        *,
        scope: SkillScope,
        manifest: SkillManifest,
    ) -> str:
        dependencies = await self._resolve_dependencies(
            scope=scope,
            manifest=manifest,
        )
        return _content_hash(manifest, dependencies)

    async def publish(
        self,
        *,
        scope: SkillScope,
        manifest: SkillManifest,
        evaluation: SkillEvaluationEvidence,
        actor_id: str,
    ) -> PublishedSkill:
        _validate_actor(actor_id)

        for inherited_scope in scope.visible_chain()[1:]:
            inherited = await self._store.get_release(
                scope=inherited_scope,
                skill_id=manifest.skill_id,
                exact_version=manifest.version,
            )
            if inherited is not None:
                raise SkillRegistryConflictError(
                    "SKILL_REGISTRY_INHERITED_VERSION_SHADOW_CONFLICT"
                )

        dependencies = await self._resolve_dependencies(
            scope=scope,
            manifest=manifest,
        )
        content_hash = _content_hash(manifest, dependencies)

        existing = await self._store.get_release(
            scope=scope,
            skill_id=manifest.skill_id,
            exact_version=manifest.version,
        )
        if existing is not None:
            if existing.content_hash != content_hash:
                raise SkillRegistryConflictError(
                    "SKILL_REGISTRY_IMMUTABLE_VERSION_CONFLICT"
                )
            return existing

        self._evaluator.validate(
            manifest=manifest,
            subject_hash=content_hash,
            evidence=evaluation,
        )
        release = PublishedSkill(
            scope=scope,
            manifest=manifest,
            dependency_hashes=tuple(
                (item.identity, item.content_hash) for item in dependencies
            ),
            content_hash=content_hash,
            provenance_ref=_provenance_ref(scope, manifest),
            evaluation=evaluation,
            published_by=actor_id,
            published_at=self._clock(),
        )
        return await self._store.put_release(release)

    async def materialize(
        self,
        *,
        skill_refs: tuple[str, ...],
        agent: ResolvedAgentConfig,
        context: DeepAgentInvocationContext,
    ) -> tuple[MaterializedSkill, ...]:
        if self._sink is None:
            raise SkillRegistryMaterializationError(
                "SKILL_REGISTRY_MATERIALIZATION_SINK_REQUIRED"
            )
        if len(skill_refs) != len(set(skill_refs)):
            raise SkillRegistryMaterializationError(
                "SKILL_REGISTRY_MATERIALIZATION_REF_DUPLICATE"
            )
        scope = SkillScope.project(
            context.organization_id,
            context.project_id,
        )
        results: list[MaterializedSkill] = []
        for ref in skill_refs:
            skill_id, exact_version = parse_skill_ref(ref)
            release = await self._resolve_exact_visible(
                scope=scope,
                skill_id=skill_id,
                exact_version=exact_version,
            )
            self._validate_runtime_permissions(
                release=release,
                agent=agent,
                context=context,
            )
            files = await self._materialization_files(release)
            await self._sink.install(
                skill_id=skill_id,
                exact_version=exact_version,
                content_hash=release.content_hash,
                files=files,
            )
            results.append(
                MaterializedSkill(
                    skill_id=skill_id,
                    exact_version=exact_version,
                    path=f"/skills/{skill_id}/{exact_version}/SKILL.md",
                    content_hash=release.content_hash,
                    required_tools=release.manifest.required_tools,
                    required_permissions=(
                        release.manifest.required_permissions
                    ),
                    provenance_ref=release.provenance_ref,
                )
            )
        return tuple(results)

    async def list_versions(
        self,
        *,
        scope: SkillScope,
        skill_id: str,
        include_inherited: bool = False,
    ) -> tuple[PublishedSkill, ...]:
        scopes = scope.visible_chain() if include_inherited else (scope,)
        seen: set[tuple[str, str]] = set()
        values: list[PublishedSkill] = []
        for candidate in scopes:
            for release in await self._store.list_releases(
                scope=candidate,
                skill_id=skill_id,
            ):
                key = (release.manifest.version, release.content_hash)
                if key not in seen:
                    seen.add(key)
                    values.append(release)
        return tuple(values)

    async def _resolve_dependencies(
        self,
        *,
        scope: SkillScope,
        manifest: SkillManifest,
    ) -> tuple[PublishedSkill, ...]:
        if manifest.identity in manifest.dependency_refs:
            raise SkillRegistryDependencyError(
                "SKILL_REGISTRY_DEPENDENCY_CYCLE"
            )
        values = []
        for ref in manifest.dependency_refs:
            skill_id, exact_version = parse_skill_ref(ref)
            dependency = await self._resolve_exact_visible(
                scope=scope,
                skill_id=skill_id,
                exact_version=exact_version,
            )
            await self._assert_acyclic_release(
                dependency,
                path=(manifest.identity,),
            )
            values.append(dependency)
        return tuple(values)

    async def _assert_acyclic_release(
        self,
        release: PublishedSkill,
        *,
        path: tuple[str, ...],
    ) -> None:
        if release.identity in path:
            raise SkillRegistryDependencyError(
                "SKILL_REGISTRY_DEPENDENCY_CYCLE"
            )
        next_path = path + (release.identity,)
        for ref in release.manifest.dependency_refs:
            skill_id, exact_version = parse_skill_ref(ref)
            child = await self._resolve_exact_visible(
                scope=release.scope,
                skill_id=skill_id,
                exact_version=exact_version,
            )
            await self._assert_acyclic_release(child, path=next_path)

    async def _resolve_exact_visible(
        self,
        *,
        scope: SkillScope,
        skill_id: str,
        exact_version: str,
    ) -> PublishedSkill:
        for candidate in scope.visible_chain():
            release = await self._store.get_release(
                scope=candidate,
                skill_id=skill_id,
                exact_version=exact_version,
            )
            if release is not None:
                return release
        raise SkillRegistryNotFoundError(
            "SKILL_REGISTRY_EXACT_VERSION_NOT_FOUND"
        )

    def _validate_runtime_permissions(
        self,
        *,
        release: PublishedSkill,
        agent: ResolvedAgentConfig,
        context: DeepAgentInvocationContext,
    ) -> None:
        tools = set(release.manifest.required_tools)
        if not tools <= set(agent.allowed_tools):
            raise SkillRegistryPermissionError(
                "SKILL_REGISTRY_TOOL_EXCEEDS_AGENT"
            )
        if not tools <= set(context.permissions.allowed_tools):
            raise SkillRegistryPermissionError(
                "SKILL_REGISTRY_TOOL_NOT_GRANTED"
            )
        for permission in release.manifest.required_permissions:
            if permission == "sandbox.execute":
                if not agent.sandbox_execute or not context.permissions.sandbox_execute:
                    raise SkillRegistryPermissionError(
                        "SKILL_REGISTRY_SANDBOX_NOT_GRANTED"
                    )
                continue
            if permission.startswith("memory.read:"):
                memory_scope = permission.removeprefix("memory.read:")
                if (
                    memory_scope not in agent.memory_read_scopes
                    or memory_scope not in context.permissions.memory_read_scopes
                ):
                    raise SkillRegistryPermissionError(
                        "SKILL_REGISTRY_MEMORY_READ_NOT_GRANTED"
                    )
                continue
            if permission.startswith("memory.write:"):
                memory_scope = permission.removeprefix("memory.write:")
                if (
                    memory_scope not in agent.memory_write_scopes
                    or memory_scope not in context.permissions.memory_write_scopes
                ):
                    raise SkillRegistryPermissionError(
                        "SKILL_REGISTRY_MEMORY_WRITE_NOT_GRANTED"
                    )
                continue
            raise SkillRegistryPermissionError(
                "SKILL_REGISTRY_PERMISSION_UNKNOWN"
            )

    async def _materialization_files(
        self,
        release: PublishedSkill,
    ) -> tuple[MaterializationFile, ...]:
        values = [
            MaterializationFile(path=item.path, content=item.content)
            for item in release.manifest.files
        ]
        dependencies = await self._dependency_closure(release)
        for dependency in dependencies:
            prefix = (
                f".lumi/dependencies/{dependency.manifest.skill_id}/"
                f"{dependency.manifest.version}"
            )
            for item in dependency.manifest.files:
                values.append(
                    MaterializationFile(
                        path=f"{prefix}/{item.path}",
                        content=item.content,
                    )
                )
        values.append(
            MaterializationFile(
                path=".lumi/dependencies.json",
                content=dependency_index(
                    tuple(
                        (item.identity, item.content_hash)
                        for item in dependencies
                    )
                ),
            )
        )
        return tuple(values)

    async def _dependency_closure(
        self,
        release: PublishedSkill,
    ) -> tuple[PublishedSkill, ...]:
        ordered: list[PublishedSkill] = []
        seen: set[str] = set()

        async def visit(parent: PublishedSkill) -> None:
            for ref in parent.manifest.dependency_refs:
                skill_id, exact_version = parse_skill_ref(ref)
                child = await self._resolve_exact_visible(
                    scope=parent.scope,
                    skill_id=skill_id,
                    exact_version=exact_version,
                )
                if child.identity in seen:
                    continue
                seen.add(child.identity)
                await visit(child)
                ordered.append(child)

        await visit(release)
        return tuple(ordered)


def _content_hash(
    manifest: SkillManifest,
    dependencies: tuple[PublishedSkill, ...],
) -> str:
    return stable_hash(
        {
            "manifest": manifest_to_dict(manifest),
            "dependency_hashes": [
                {
                    "ref": item.identity,
                    "content_hash": item.content_hash,
                }
                for item in dependencies
            ],
        }
    )


def _provenance_ref(scope: SkillScope, manifest: SkillManifest) -> str:
    if scope.project_id is not None:
        prefix = f"project/{scope.organization_id}/{scope.project_id}"
    elif scope.organization_id is not None:
        prefix = f"organization/{scope.organization_id}"
    else:
        prefix = "global"
    return f"skill-registry://{prefix}/{manifest.skill_id}/{manifest.version}"


def _validate_actor(actor_id: str) -> None:
    if not actor_id or len(actor_id) > 255:
        raise SkillRegistryPublicationError(
            "SKILL_REGISTRY_ACTOR_INVALID"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
