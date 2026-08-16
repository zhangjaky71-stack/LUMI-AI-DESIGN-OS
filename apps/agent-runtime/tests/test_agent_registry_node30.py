from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from lumi_agent_runtime.agent_registry import (
    AgentManifest,
    AgentRegistry,
    AgentRegistryAliasError,
    AgentRegistryConflictError,
    AgentRegistryNotFoundError,
    AgentScope,
    GitWorkspaceAgentRegistryStore,
    InMemoryAgentRegistryStore,
)
from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    PermissionScope,
)


def _manifest(
    agent_id: str,
    version: str,
    *,
    prompt: str | None = None,
    subagents: tuple[str, ...] = (),
    tools: tuple[str, ...] = ("web.search",),
) -> AgentManifest:
    return AgentManifest(
        agent_id=agent_id,
        version=version,
        role=agent_id.replace("-", " ").title(),
        description=f"{agent_id} fixture",
        system_prompt=prompt or f"Operate as {agent_id}.",
        model_profile="balanced",
        allowed_tools=tools,
        skill_refs=("web-research@1.0.0",),
        context_policy="project-pinned-v1",
        memory_read_scopes=("project",),
        memory_write_scopes=("project",),
        subagent_refs=subagents,
    )


def _context(org_id, project_id) -> DeepAgentInvocationContext:
    return DeepAgentInvocationContext(
        organization_id=org_id,
        project_id=project_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        actor_id="user:test",
        root_agent="creative-director",
        permissions=PermissionScope(
            allowed_tools=("web.search",),
            memory_read_scopes=("project",),
            memory_write_scopes=("project",),
            allowed_subagents=("researcher",),
        ),
        budget_limit_usd="5.00",
    )


def test_exact_versions_are_immutable_and_idempotent() -> None:
    async def run() -> None:
        store = InMemoryAgentRegistryStore()
        registry = AgentRegistry(store, clock=lambda: "2026-08-17T00:00:00Z")
        scope = AgentScope.global_scope()
        first = await registry.publish(
            scope=scope,
            manifest=_manifest("researcher", "1.0.0"),
            actor_id="release:test",
        )
        same = await registry.publish(
            scope=scope,
            manifest=_manifest("researcher", "1.0.0"),
            actor_id="release:other",
        )
        assert same.content_hash == first.content_hash
        with pytest.raises(AgentRegistryConflictError):
            await registry.publish(
                scope=scope,
                manifest=_manifest(
                    "researcher",
                    "1.0.0",
                    prompt="Mutated prompt must not overwrite exact version.",
                ),
                actor_id="release:test",
            )

    asyncio.run(run())


def test_alias_promotion_and_rollback_do_not_mutate_releases() -> None:
    async def run() -> None:
        registry = AgentRegistry(
            InMemoryAgentRegistryStore(),
            clock=lambda: "2026-08-17T00:00:00Z",
        )
        scope = AgentScope.global_scope()
        for version in ("1.0.0", "1.1.0"):
            await registry.publish(
                scope=scope,
                manifest=_manifest("researcher", version),
                actor_id="release:test",
            )
        first = await registry.promote(
            scope=scope,
            agent_id="researcher",
            alias="stable",
            exact_version="1.0.0",
            actor_id="release:test",
        )
        assert first.revision == 1
        second = await registry.promote(
            scope=scope,
            agent_id="researcher",
            alias="stable",
            exact_version="1.1.0",
            actor_id="release:test",
        )
        assert second.history == ("1.0.0",)
        rolled = await registry.rollback_alias(
            scope=scope,
            agent_id="researcher",
            alias="stable",
            actor_id="release:test",
        )
        assert rolled.exact_version == "1.0.0"
        assert rolled.revision == 3
        with pytest.raises(AgentRegistryAliasError):
            await registry.rollback_alias(
                scope=scope,
                agent_id="researcher",
                alias="stable",
                actor_id="release:test",
            )

    asyncio.run(run())


def test_tenant_visibility_is_project_org_global_only() -> None:
    async def run() -> None:
        registry = AgentRegistry(InMemoryAgentRegistryStore())
        org_a, org_b = uuid4(), uuid4()
        project_a, project_b = uuid4(), uuid4()
        await registry.publish(
            scope=AgentScope.project(org_a, project_a),
            manifest=_manifest("creative-director", "1.0.0"),
            actor_id="release:test",
        )
        resolved = await registry.resolve(
            agent_ref="creative-director@1.0.0",
            context=_context(org_a, project_a),
        )
        assert resolved.exact_version == "1.0.0"
        with pytest.raises(AgentRegistryNotFoundError):
            await registry.resolve(
                agent_ref="creative-director@1.0.0",
                context=_context(org_b, project_b),
            )

        await registry.publish(
            scope=AgentScope.global_scope(),
            manifest=_manifest("researcher", "1.0.0"),
            actor_id="release:test",
        )
        with pytest.raises(AgentRegistryConflictError):
            await registry.publish(
                scope=AgentScope.project(org_a, project_a),
                manifest=_manifest("researcher", "1.0.0"),
                actor_id="release:test",
            )

    asyncio.run(run())


def test_publish_pins_subagent_alias_and_hash_is_stable() -> None:
    async def run() -> None:
        store = InMemoryAgentRegistryStore()
        registry = AgentRegistry(
            store,
            clock=lambda: "2026-08-17T00:00:00Z",
        )
        scope = AgentScope.global_scope()
        child_v1 = await registry.publish(
            scope=scope,
            manifest=_manifest("researcher", "1.0.0"),
            actor_id="release:test",
        )
        await registry.promote(
            scope=scope,
            agent_id="researcher",
            alias="stable",
            exact_version="1.0.0",
            actor_id="release:test",
        )
        root = await registry.publish(
            scope=scope,
            manifest=_manifest(
                "creative-director",
                "2.0.0",
                subagents=("researcher@stable",),
            ),
            actor_id="release:test",
        )
        assert root.manifest.subagent_refs == ("researcher@1.0.0",)

        child_v2 = await registry.publish(
            scope=scope,
            manifest=_manifest("researcher", "1.1.0"),
            actor_id="release:test",
        )
        assert child_v1.content_hash != child_v2.content_hash
        await registry.promote(
            scope=scope,
            agent_id="researcher",
            alias="stable",
            exact_version="1.1.0",
            actor_id="release:test",
        )

        replay = await registry.publish(
            scope=scope,
            manifest=_manifest(
                "creative-director",
                "2.0.0",
                subagents=("researcher@1.0.0",),
            ),
            actor_id="release:other",
        )
        assert replay.content_hash == root.content_hash

    asyncio.run(run())


def test_registry_implements_node29_resolver_contract() -> None:
    async def run() -> None:
        registry = AgentRegistry(InMemoryAgentRegistryStore())
        org_id, project_id = uuid4(), uuid4()
        scope = AgentScope.project(org_id, project_id)
        await registry.publish(
            scope=scope,
            manifest=_manifest("researcher", "1.0.0"),
            actor_id="release:test",
        )
        await registry.publish(
            scope=scope,
            manifest=_manifest(
                "creative-director",
                "1.0.0",
                subagents=("researcher@1.0.0",),
            ),
            actor_id="release:test",
        )
        resolved = await registry.resolve(
            agent_ref="creative-director@1.0.0",
            context=_context(org_id, project_id),
        )
        assert resolved.identity == "creative-director@1.0.0"
        assert resolved.content_hash
        assert resolved.provenance_ref.startswith("agent-registry://")
        assert resolved.subagents[0].exact_version == "1.0.0"
        assert resolved.subagents[0].provenance_ref.startswith(
            "agent-registry://"
        )

    asyncio.run(run())


def test_git_workspace_store_round_trip(tmp_path: Path) -> None:
    async def run() -> None:
        store = GitWorkspaceAgentRegistryStore(tmp_path)
        registry = AgentRegistry(
            store,
            clock=lambda: "2026-08-17T00:00:00Z",
        )
        scope = AgentScope.global_scope()
        release = await registry.publish(
            scope=scope,
            manifest=_manifest("researcher", "1.0.0"),
            actor_id="release:test",
        )
        await registry.promote(
            scope=scope,
            agent_id="researcher",
            alias="stable",
            exact_version="1.0.0",
            actor_id="release:test",
        )
        reloaded = GitWorkspaceAgentRegistryStore(tmp_path)
        stored = await reloaded.get_release(
            scope=scope,
            agent_id="researcher",
            exact_version="1.0.0",
        )
        alias = await reloaded.get_alias(
            scope=scope,
            agent_id="researcher",
            alias="stable",
        )
        assert stored is not None
        assert stored.content_hash == release.content_hash
        assert alias is not None
        assert alias.exact_version == "1.0.0"
        assert list(tmp_path.rglob("versions/1.0.0.json"))
        assert list(tmp_path.rglob("aliases/stable.json"))

    asyncio.run(run())
