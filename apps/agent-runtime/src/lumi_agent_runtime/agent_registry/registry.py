from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    ResolvedAgentConfig,
    ResolvedSubagent,
    stable_hash,
)

from .contracts import (
    AgentAlias,
    AgentManifest,
    AgentScope,
    PublishedAgent,
    manifest_to_dict,
    parse_agent_ref,
    validate_alias,
)
from .errors import (
    AgentRegistryAliasError,
    AgentRegistryConflictError,
    AgentRegistryNotFoundError,
    AgentRegistryPublicationError,
)
from .store import AgentRegistryStore

Clock = Callable[[], str]


class AgentRegistry:
    def __init__(
        self,
        store: AgentRegistryStore,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or _utc_now

    async def publish(
        self,
        *,
        scope: AgentScope,
        manifest: AgentManifest,
        actor_id: str,
    ) -> PublishedAgent:
        _validate_actor(actor_id)

        for inherited_scope in scope.visible_chain()[1:]:
            inherited = await self._store.get_release(
                scope=inherited_scope,
                agent_id=manifest.agent_id,
                exact_version=manifest.version,
            )
            if inherited is not None:
                raise AgentRegistryConflictError(
                    "AGENT_REGISTRY_INHERITED_VERSION_SHADOW_CONFLICT"
                )

        pinned_refs: list[str] = []
        child_releases: list[PublishedAgent] = []
        for ref in manifest.subagent_refs:
            child_id, selector = parse_agent_ref(ref)
            child = await self._resolve_release(
                scope=scope,
                agent_id=child_id,
                selector=selector,
            )
            pinned_refs.append(
                f"{child.manifest.agent_id}@{child.manifest.version}"
            )
            child_releases.append(child)

        normalized = manifest.with_pinned_subagents(tuple(pinned_refs))
        content_hash = stable_hash(
            {
                "manifest": manifest_to_dict(normalized),
                "subagent_hashes": [
                    {
                        "ref": release.identity,
                        "content_hash": release.content_hash,
                    }
                    for release in child_releases
                ],
            }
        )
        release = PublishedAgent(
            scope=scope,
            manifest=normalized,
            content_hash=content_hash,
            provenance_ref=_provenance_ref(scope, normalized),
            published_by=actor_id,
            published_at=self._clock(),
        )

        self._to_runtime_config(release, tuple(child_releases))
        return await self._store.put_release(release)

    async def promote(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        alias: str,
        exact_version: str,
        actor_id: str,
    ) -> AgentAlias:
        parse_agent_ref(f"{agent_id}@{exact_version}")
        validate_alias(alias)
        _validate_actor(actor_id)
        release = await self._store.get_release(
            scope=scope,
            agent_id=agent_id,
            exact_version=exact_version,
        )
        if release is None:
            raise AgentRegistryNotFoundError(
                "AGENT_REGISTRY_PROMOTION_TARGET_NOT_FOUND"
            )
        if await self._store.get_release(
            scope=scope,
            agent_id=agent_id,
            exact_version=alias,
        ) is not None:
            raise AgentRegistryAliasError(
                "AGENT_REGISTRY_ALIAS_SHADOWS_EXACT_VERSION"
            )
        current = await self._store.get_alias(
            scope=scope,
            agent_id=agent_id,
            alias=alias,
        )
        if current is not None and current.exact_version == exact_version:
            return current
        value = AgentAlias(
            scope=scope,
            agent_id=agent_id,
            alias=alias,
            exact_version=exact_version,
            history=(
                current.history + (current.exact_version,)
                if current is not None
                else ()
            ),
            revision=(current.revision + 1 if current is not None else 1),
            updated_by=actor_id,
            updated_at=self._clock(),
        )
        return await self._store.put_alias(value)

    async def rollback_alias(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        alias: str,
        actor_id: str,
    ) -> AgentAlias:
        parse_agent_ref(f"{agent_id}@1")
        validate_alias(alias)
        _validate_actor(actor_id)
        current = await self._store.get_alias(
            scope=scope,
            agent_id=agent_id,
            alias=alias,
        )
        if current is None:
            raise AgentRegistryAliasError(
                "AGENT_REGISTRY_ALIAS_NOT_FOUND"
            )
        if not current.history:
            raise AgentRegistryAliasError(
                "AGENT_REGISTRY_ALIAS_NO_ROLLBACK"
            )
        target = current.history[-1]
        release = await self._store.get_release(
            scope=scope,
            agent_id=agent_id,
            exact_version=target,
        )
        if release is None:
            raise AgentRegistryConflictError(
                "AGENT_REGISTRY_ALIAS_HISTORY_TARGET_MISSING"
            )
        value = replace(
            current,
            exact_version=target,
            history=current.history[:-1],
            revision=current.revision + 1,
            updated_by=actor_id,
            updated_at=self._clock(),
        )
        return await self._store.put_alias(value)

    async def resolve(
        self,
        *,
        agent_ref: str,
        context: DeepAgentInvocationContext,
    ) -> ResolvedAgentConfig:
        agent_id, selector = parse_agent_ref(agent_ref)
        scope = AgentScope.project(
            context.organization_id,
            context.project_id,
        )
        release = await self._resolve_release(
            scope=scope,
            agent_id=agent_id,
            selector=selector,
        )
        children = []
        for child_ref in release.manifest.subagent_refs:
            child_id, exact_version = parse_agent_ref(child_ref)
            child = await self._resolve_exact_visible(
                scope=release.scope,
                agent_id=child_id,
                exact_version=exact_version,
            )
            children.append(child)
        return self._to_runtime_config(release, tuple(children))

    async def list_versions(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        include_inherited: bool = False,
    ) -> tuple[PublishedAgent, ...]:
        scopes = scope.visible_chain() if include_inherited else (scope,)
        seen: set[tuple[str, str]] = set()
        values: list[PublishedAgent] = []
        for candidate in scopes:
            for release in await self._store.list_releases(
                scope=candidate,
                agent_id=agent_id,
            ):
                key = (release.manifest.version, release.content_hash)
                if key not in seen:
                    seen.add(key)
                    values.append(release)
        return tuple(values)

    async def _resolve_release(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        selector: str,
    ) -> PublishedAgent:
        exact = await self._resolve_exact_visible(
            scope=scope,
            agent_id=agent_id,
            exact_version=selector,
            required=False,
        )
        if exact is not None:
            return exact

        for candidate in scope.visible_chain():
            alias = await self._store.get_alias(
                scope=candidate,
                agent_id=agent_id,
                alias=selector,
            )
            if alias is None:
                continue
            release = await self._store.get_release(
                scope=candidate,
                agent_id=agent_id,
                exact_version=alias.exact_version,
            )
            if release is None:
                raise AgentRegistryConflictError(
                    "AGENT_REGISTRY_ALIAS_TARGET_MISSING"
                )
            return release
        raise AgentRegistryNotFoundError("AGENT_REGISTRY_REF_NOT_FOUND")

    async def _resolve_exact_visible(
        self,
        *,
        scope: AgentScope,
        agent_id: str,
        exact_version: str,
        required: bool = True,
    ) -> PublishedAgent | None:
        for candidate in scope.visible_chain():
            release = await self._store.get_release(
                scope=candidate,
                agent_id=agent_id,
                exact_version=exact_version,
            )
            if release is not None:
                return release
        if required:
            raise AgentRegistryNotFoundError(
                "AGENT_REGISTRY_EXACT_VERSION_NOT_FOUND"
            )
        return None

    @staticmethod
    def _to_runtime_config(
        release: PublishedAgent,
        children: tuple[PublishedAgent, ...],
    ) -> ResolvedAgentConfig:
        manifest = release.manifest
        resolved_children = tuple(
            ResolvedSubagent(
                agent_id=child.manifest.agent_id,
                exact_version=child.manifest.version,
                role=child.manifest.role,
                description=child.manifest.description,
                system_prompt=child.manifest.system_prompt,
                model_profile=child.manifest.model_profile,
                allowed_tools=child.manifest.allowed_tools,
                skill_refs=child.manifest.skill_refs,
                output_schema=child.manifest.output_schema,
                max_steps=child.manifest.max_steps,
                provenance_ref=child.provenance_ref,
            )
            for child in children
        )
        return ResolvedAgentConfig(
            agent_id=manifest.agent_id,
            exact_version=manifest.version,
            role=manifest.role,
            system_prompt=manifest.system_prompt,
            model_profile=manifest.model_profile,
            allowed_tools=manifest.allowed_tools,
            skill_refs=manifest.skill_refs,
            context_policy=manifest.context_policy,
            memory_read_scopes=manifest.memory_read_scopes,
            memory_write_scopes=manifest.memory_write_scopes,
            sandbox_execute=manifest.sandbox_execute,
            subagents=resolved_children,
            output_schema=manifest.output_schema,
            max_steps=manifest.max_steps,
            delegation=manifest.delegation,
            provenance_ref=release.provenance_ref,
            content_hash=release.content_hash,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provenance_ref(
    scope: AgentScope,
    manifest: AgentManifest,
) -> str:
    if scope.project_id is not None:
        prefix = (
            f"project/{scope.organization_id}/{scope.project_id}"
        )
    elif scope.organization_id is not None:
        prefix = f"organization/{scope.organization_id}"
    else:
        prefix = "global"
    return (
        f"agent-registry://{prefix}/{manifest.agent_id}/{manifest.version}"
    )


def _validate_actor(actor_id: str) -> None:
    if not actor_id or len(actor_id) > 255:
        raise AgentRegistryPublicationError("AGENT_REGISTRY_ACTOR_INVALID")
