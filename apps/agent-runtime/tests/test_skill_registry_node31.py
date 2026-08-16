from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    PermissionScope,
    ResolvedAgentConfig,
)
from lumi_agent_runtime.skill_registry import (
    AtomicDirectorySkillPackageSink,
    GitWorkspaceSkillRegistryStore,
    InMemorySkillPackageSink,
    InMemorySkillRegistryStore,
    SkillEvalStatus,
    SkillEvaluationEvidence,
    SkillFile,
    SkillManifest,
    SkillRegistry,
    SkillRegistryConflictError,
    SkillRegistryDependencyError,
    SkillRegistryEvaluationError,
    SkillRegistryNotFoundError,
    SkillRegistryPermissionError,
    SkillScope,
)

_NOW = "2026-08-17T00:00:00Z"


def _manifest(
    skill_id: str,
    version: str,
    *,
    body: str | None = None,
    dependencies: tuple[str, ...] = (),
    tools: tuple[str, ...] = (),
    permissions: tuple[str, ...] = (),
) -> SkillManifest:
    return SkillManifest(
        skill_id=skill_id,
        version=version,
        description=f"{skill_id} fixture",
        files=(
            SkillFile(
                path="SKILL.md",
                content=body or f"# {skill_id}\n",
            ),
        ),
        dependency_refs=dependencies,
        required_tools=tools,
        required_permissions=permissions,
    )


def _evidence(
    subject_hash: str,
    *,
    score: str = "0.90",
    status: SkillEvalStatus = SkillEvalStatus.PASSED,
) -> SkillEvaluationEvidence:
    return SkillEvaluationEvidence(
        policy_id="skill-publish-v1",
        suite_id="node31-unit",
        status=status,
        score=score,
        subject_hash=subject_hash,
        evidence_ref="eval://node31/unit",
        evaluated_at=_NOW,
    )


def _agent(
    *,
    tools: tuple[str, ...] = ("web.search",),
    execute: bool = False,
) -> ResolvedAgentConfig:
    return ResolvedAgentConfig(
        agent_id="creative-director",
        exact_version="1.0.0",
        role="Creative Director",
        system_prompt="Create a bounded design direction.",
        model_profile="balanced",
        allowed_tools=tools,
        skill_refs=(),
        context_policy="project-pinned-v1",
        memory_read_scopes=("project",),
        memory_write_scopes=("project",),
        sandbox_execute=execute,
        subagents=(),
        content_hash="a" * 64,
    )


def _context(
    organization_id,
    project_id,
    *,
    tools: tuple[str, ...] = ("web.search",),
    execute: bool = False,
) -> DeepAgentInvocationContext:
    return DeepAgentInvocationContext(
        organization_id=organization_id,
        project_id=project_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        actor_id="user:node31",
        root_agent="creative-director",
        permissions=PermissionScope(
            allowed_tools=tools,
            sandbox_execute=execute,
            memory_read_scopes=("project",),
            memory_write_scopes=("project",),
        ),
        budget_limit_usd="5.00",
    )


async def _publish(
    registry: SkillRegistry,
    scope: SkillScope,
    manifest: SkillManifest,
):
    subject = await registry.publication_subject_hash(
        scope=scope,
        manifest=manifest,
    )
    return await registry.publish(
        scope=scope,
        manifest=manifest,
        evaluation=_evidence(subject),
        actor_id="release:node31",
    )


def test_exact_skill_versions_are_immutable_and_idempotent() -> None:
    async def run() -> None:
        registry = SkillRegistry(InMemorySkillRegistryStore())
        scope = SkillScope.global_scope()
        manifest = _manifest("web-research", "1.0.0")
        first = await _publish(registry, scope, manifest)
        same = await _publish(registry, scope, manifest)
        assert same.content_hash == first.content_hash

        changed = _manifest(
            "web-research",
            "1.0.0",
            body="# changed content\n",
        )
        subject = await registry.publication_subject_hash(
            scope=scope,
            manifest=changed,
        )
        with pytest.raises(SkillRegistryConflictError):
            await registry.publish(
                scope=scope,
                manifest=changed,
                evaluation=_evidence(subject),
                actor_id="release:node31",
            )

    asyncio.run(run())


def test_eval_gate_binds_evidence_to_exact_subject() -> None:
    async def run() -> None:
        registry = SkillRegistry(InMemorySkillRegistryStore())
        scope = SkillScope.global_scope()
        manifest = _manifest("web-research", "1.0.0")
        with pytest.raises(SkillRegistryEvaluationError):
            await registry.publish(
                scope=scope,
                manifest=manifest,
                evaluation=_evidence("0" * 64),
                actor_id="release:node31",
            )

        subject = await registry.publication_subject_hash(
            scope=scope,
            manifest=manifest,
        )
        with pytest.raises(SkillRegistryEvaluationError):
            await registry.publish(
                scope=scope,
                manifest=manifest,
                evaluation=_evidence(subject, score="0.50"),
                actor_id="release:node31",
            )

    asyncio.run(run())


def test_dependency_hashes_are_part_of_runtime_content_identity() -> None:
    async def run() -> None:
        registry = SkillRegistry(InMemorySkillRegistryStore())
        scope = SkillScope.global_scope()
        base_v1 = await _publish(
            registry,
            scope,
            _manifest("brand-rules", "1.0.0"),
        )
        root_v1 = await _publish(
            registry,
            scope,
            _manifest(
                "creative-direction",
                "1.0.0",
                dependencies=("brand-rules@1.0.0",),
            ),
        )
        base_v2 = await _publish(
            registry,
            scope,
            _manifest(
                "brand-rules",
                "1.1.0",
                body="# new rules\n",
            ),
        )
        root_v2 = await _publish(
            registry,
            scope,
            _manifest(
                "creative-direction",
                "1.1.0",
                dependencies=("brand-rules@1.1.0",),
            ),
        )
        assert base_v1.content_hash != base_v2.content_hash
        assert root_v1.content_hash != root_v2.content_hash
        assert root_v1.dependency_hashes == (
            ("brand-rules@1.0.0", base_v1.content_hash),
        )

    asyncio.run(run())


def test_dependency_cycle_and_inherited_exact_shadow_fail_closed() -> None:
    async def run() -> None:
        registry = SkillRegistry(InMemorySkillRegistryStore())
        global_scope = SkillScope.global_scope()
        cyclic = _manifest(
            "loop-skill",
            "1.0.0",
            dependencies=("loop-skill@1.0.0",),
        )
        with pytest.raises(SkillRegistryDependencyError):
            await registry.publication_subject_hash(
                scope=global_scope,
                manifest=cyclic,
            )

        await _publish(
            registry,
            global_scope,
            _manifest("web-research", "1.0.0"),
        )
        with pytest.raises(SkillRegistryConflictError):
            await _publish(
                registry,
                SkillScope.project(uuid4(), uuid4()),
                _manifest("web-research", "1.0.0"),
            )

    asyncio.run(run())


def test_project_skill_is_not_visible_to_other_tenant() -> None:
    async def run() -> None:
        sink = InMemorySkillPackageSink()
        registry = SkillRegistry(
            InMemorySkillRegistryStore(),
            sink=sink,
        )
        org_a, org_b = uuid4(), uuid4()
        project_a, project_b = uuid4(), uuid4()
        await _publish(
            registry,
            SkillScope.project(org_a, project_a),
            _manifest("private-brand", "1.0.0"),
        )
        with pytest.raises(SkillRegistryNotFoundError):
            await registry.materialize(
                skill_refs=("private-brand@1.0.0",),
                agent=_agent(),
                context=_context(org_b, project_b),
            )

    asyncio.run(run())


def test_materializer_returns_only_requested_skill_and_embeds_dependencies() -> None:
    async def run() -> None:
        sink = InMemorySkillPackageSink()
        registry = SkillRegistry(
            InMemorySkillRegistryStore(),
            sink=sink,
        )
        scope = SkillScope.global_scope()
        await _publish(
            registry,
            scope,
            _manifest("brand-rules", "1.0.0"),
        )
        await _publish(
            registry,
            scope,
            _manifest(
                "creative-direction",
                "1.0.0",
                dependencies=("brand-rules@1.0.0",),
                tools=("web.search",),
            ),
        )
        org_id, project_id = uuid4(), uuid4()
        materialized = await registry.materialize(
            skill_refs=("creative-direction@1.0.0",),
            agent=_agent(),
            context=_context(org_id, project_id),
        )
        assert len(materialized) == 1
        assert materialized[0].path == (
            "/skills/creative-direction/1.0.0/SKILL.md"
        )
        _, files = sink.installed[("creative-direction", "1.0.0")]
        assert (
            ".lumi/dependencies/brand-rules/1.0.0/SKILL.md"
            in files
        )
        assert ".lumi/dependencies.json" in files

    asyncio.run(run())


def test_materializer_enforces_runtime_tool_and_permission_grants() -> None:
    async def run() -> None:
        registry = SkillRegistry(
            InMemorySkillRegistryStore(),
            sink=InMemorySkillPackageSink(),
        )
        scope = SkillScope.global_scope()
        await _publish(
            registry,
            scope,
            _manifest(
                "shell-skill",
                "1.0.0",
                permissions=("sandbox.execute",),
            ),
        )
        org_id, project_id = uuid4(), uuid4()
        with pytest.raises(SkillRegistryPermissionError):
            await registry.materialize(
                skill_refs=("shell-skill@1.0.0",),
                agent=_agent(execute=False),
                context=_context(org_id, project_id, execute=False),
            )

    asyncio.run(run())


def test_git_store_and_atomic_directory_sink_round_trip(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        registry_root = tmp_path / "registry"
        materialized_root = tmp_path / "materialized"
        store = GitWorkspaceSkillRegistryStore(registry_root)
        registry = SkillRegistry(
            store,
            sink=AtomicDirectorySkillPackageSink(materialized_root),
            clock=lambda: _NOW,
        )
        scope = SkillScope.global_scope()
        release = await _publish(
            registry,
            scope,
            _manifest("web-research", "1.0.0"),
        )

        reloaded = GitWorkspaceSkillRegistryStore(registry_root)
        stored = await reloaded.get_release(
            scope=scope,
            skill_id="web-research",
            exact_version="1.0.0",
        )
        assert stored is not None
        assert stored.content_hash == release.content_hash

        org_id, project_id = uuid4(), uuid4()
        await registry.materialize(
            skill_refs=("web-research@1.0.0",),
            agent=_agent(),
            context=_context(org_id, project_id),
        )
        assert (
            materialized_root
            / "web-research"
            / "1.0.0"
            / "SKILL.md"
        ).exists()

    asyncio.run(run())
