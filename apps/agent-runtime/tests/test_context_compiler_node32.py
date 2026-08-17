from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from lumi_agent_runtime.context_compiler import (
    CONSTRAINT_TYPES,
    SOURCE_PRIORITY,
    ConstraintScopeSnapshot,
    ConstraintStrength,
    ContextBundleIntegrityError,
    ContextBundleProviderAdapter,
    ContextCompileRequest,
    ContextCompiler,
    ContextConflictError,
    ContextConstraint,
    ContextFact,
    ContextFactChannel,
    ContextScopeKind,
    ContextSourcePermissionError,
    ContextSourceSnapshot,
    ContextSourceType,
    ContextSourceValidationError,
    GitWorkspaceContextBundleStore,
    InMemoryContextBundleStore,
    NormalizedRectSnapshot,
)
from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    PermissionScope,
)

ORG = UUID("11111111-1111-1111-1111-111111111111")
PROJECT = UUID("22222222-2222-2222-2222-222222222222")
TASK = UUID("33333333-3333-3333-3333-333333333333")
RUN = UUID("44444444-4444-4444-4444-444444444444")
OP = UUID("55555555-5555-5555-5555-555555555555")
C1 = UUID("0191d5a0-0000-7000-8000-000000000001")
C2 = UUID("0191d5a0-0000-7000-8000-000000000002")
C3 = UUID("0191d5a0-0000-7000-8000-000000000003")
C4 = UUID("0191d5a0-0000-7000-8000-000000000004")
C5 = UUID("0191d5a0-0000-7000-8000-000000000005")


def run(value):
    return asyncio.run(value)


def request(*, scopes=("organization", "project", "brand", "user")):
    return ContextCompileRequest(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        memory_read_scopes=scopes,
        brand_id="brand-a",
        user_id="user-a",
    )


def source(
    name: str,
    source_type: ContextSourceType,
    scope_kind: ContextScopeKind,
    scope_id: str,
    *,
    constraints: tuple[ContextConstraint, ...] = (),
    fact: ContextFact | None = None,
    source_text: str = "",
):
    return ContextSourceSnapshot.build(
        source_ref=f"context-source://{name}/v1",
        source_type=source_type,
        scope_kind=scope_kind,
        scope_id=scope_id,
        version="1",
        constraints=constraints,
        facts=(fact,) if fact else (),
        source_text=source_text,
    )


def invocation(*, scopes=("organization", "project", "brand", "user"), task_id=TASK):
    return DeepAgentInvocationContext(
        organization_id=ORG,
        project_id=PROJECT,
        agent_run_id=RUN,
        task_id=task_id,
        operation_id=OP,
        actor_id="tester",
        root_agent="designer",
        permissions=PermissionScope(allowed_tools=(), memory_read_scopes=scopes),
        budget_limit_usd="1",
    )


def constraint(
    cid: UUID,
    *,
    kind: str = "LOCK_POSITION",
    strength: ConstraintStrength = ConstraintStrength.HARD,
    priority: int = 0,
    parameters: dict | None = None,
    scope: ConstraintScopeSnapshot | None = None,
    active: bool = True,
):
    return ContextConstraint(
        constraint_id=cid,
        constraint_type=kind,
        strength=strength,
        priority=priority,
        parameters=parameters or {"position": "top-left"},
        scope=scope or ConstraintScopeSnapshot(),
        active=active,
    )


def test_node14_v1_constraint_vocabulary_and_priority_are_frozen():
    assert len(CONSTRAINT_TYPES) == 24
    assert CONSTRAINT_TYPES[0] == "LOCK_POSITION"
    assert CONSTRAINT_TYPES[-1] == "REQUIRE_IDENTITY_SCORE"
    assert tuple(item.value for item in SOURCE_PRIORITY) == (
        "SAFETY_SYSTEM",
        "USER_EXPLICIT",
        "APPROVED_BRAND_RULE",
        "PROJECT_RULE",
        "RECIPE_RULE",
        "AGENT_INFERRED",
        "STYLE_PREFERENCE",
    )
    with pytest.raises(ContextSourceValidationError, match="TYPE_INVALID"):
        constraint(C1, kind="CUSTOM_CONSTRAINT")


def test_user_explicit_shadows_brand_using_node14_group_semantics():
    brand = source(
        "brand",
        ContextSourceType.APPROVED_BRAND_RULE,
        ContextScopeKind.BRAND,
        "brand-a",
        constraints=(constraint(C1, parameters={"position": "top-left"}),),
    )
    user = source(
        "user",
        ContextSourceType.USER_EXPLICIT,
        ContextScopeKind.TASK,
        str(TASK),
        constraints=(constraint(C2, parameters={"position": "top-right"}),),
    )
    bundle = run(
        ContextCompiler(InMemoryContextBundleStore()).compile(
            request=request(), sources=(brand, user)
        )
    )
    payload = json.loads(bundle.pinned_constraints)
    effective = payload["constraint_set"]["constraints"]
    assert len(effective) == 1
    assert effective[0]["id"] == str(C2)
    assert effective[0]["type"] == "LOCK_POSITION"
    assert effective[0]["source"] == "USER_EXPLICIT"
    assert effective[0]["parameters"] == {"position": "top-right"}
    assert payload["shadowed"][0]["reason"] == "lower_source_priority"


def test_safety_system_cannot_be_shadowed_by_user_explicit():
    safety = source(
        "safety",
        ContextSourceType.SAFETY_SYSTEM,
        ContextScopeKind.ORGANIZATION,
        str(ORG),
        constraints=(
            constraint(
                C1,
                kind="LOCK_CONTENT",
                strength=ConstraintStrength.HARD,
                parameters={"mode": "strict"},
            ),
        ),
    )
    user = source(
        "user",
        ContextSourceType.USER_EXPLICIT,
        ContextScopeKind.TASK,
        str(TASK),
        constraints=(
            constraint(
                C2,
                kind="LOCK_CONTENT",
                strength=ConstraintStrength.ADVISORY,
                parameters={"mode": "off"},
            ),
        ),
    )
    bundle = run(
        ContextCompiler(InMemoryContextBundleStore()).compile(
            request=request(scopes=()), sources=(user, safety)
        )
    )
    effective = json.loads(bundle.pinned_constraints)["constraint_set"][
        "constraints"
    ][0]
    assert effective["source"] == "SAFETY_SYSTEM"
    assert effective["severity"] == "HARD"
    assert effective["parameters"] == {"mode": "strict"}


def test_node14_priority_then_severity_then_id_resolution_is_preserved():
    project = source(
        "project",
        ContextSourceType.PROJECT_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        constraints=(
            constraint(C1, priority=10, parameters={"position": "left"}),
            constraint(
                C2,
                priority=20,
                strength=ConstraintStrength.SOFT,
                parameters={"position": "right"},
            ),
        ),
    )
    bundle = run(
        ContextCompiler(InMemoryContextBundleStore()).compile(
            request=request(scopes=("project",)), sources=(project,)
        )
    )
    effective = json.loads(bundle.pinned_constraints)["constraint_set"][
        "constraints"
    ][0]
    assert effective["id"] == str(C2)
    assert effective["priority"] == 20

    project2 = source(
        "project2",
        ContextSourceType.PROJECT_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        constraints=(
            constraint(
                C3,
                priority=30,
                strength=ConstraintStrength.SOFT,
                parameters={"position": "center"},
            ),
            constraint(
                C4,
                priority=30,
                strength=ConstraintStrength.HARD,
                parameters={"position": "center"},
            ),
            constraint(
                C5,
                priority=30,
                strength=ConstraintStrength.HARD,
                parameters={"position": "center"},
            ),
        ),
    )
    second = run(
        ContextCompiler(InMemoryContextBundleStore()).compile(
            request=request(scopes=("project",)), sources=(project2,)
        )
    )
    effective2 = json.loads(second.pinned_constraints)["constraint_set"][
        "constraints"
    ][0]
    assert effective2["severity"] == "HARD"
    assert effective2["id"] == str(C4)


def test_same_level_constraint_parameter_conflict_is_explicit():
    first = source(
        "project-a",
        ContextSourceType.PROJECT_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        constraints=(constraint(C1, priority=20, parameters={"position": "left"}),),
    )
    second = source(
        "project-b",
        ContextSourceType.PROJECT_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        constraints=(constraint(C2, priority=20, parameters={"position": "right"}),),
    )
    with pytest.raises(ContextConflictError) as exc:
        run(
            ContextCompiler(InMemoryContextBundleStore()).compile(
                request=request(scopes=("project",)), sources=(second, first)
            )
        )
    assert exc.value.conflicts[0].channel == "constraint"
    assert exc.value.conflicts[0].constraint_ids == (str(C1), str(C2))
    assert len(exc.value.conflicts[0].fingerprints) == 2


def test_same_level_fact_conflict_is_explicit_and_identical_merges_provenance():
    first = source(
        "recipe-a",
        ContextSourceType.RECIPE_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        fact=ContextFact("canvas.ratio", "1:1"),
    )
    second = source(
        "recipe-b",
        ContextSourceType.RECIPE_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        fact=ContextFact("canvas.ratio", "4:5"),
    )
    with pytest.raises(ContextConflictError):
        run(
            ContextCompiler(InMemoryContextBundleStore()).compile(
                request=request(scopes=("project",)), sources=(first, second)
            )
        )

    same = ContextFact("campaign.season", "summer")
    a = source(
        "same-a",
        ContextSourceType.RECIPE_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        fact=same,
    )
    b = source(
        "same-b",
        ContextSourceType.RECIPE_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        fact=same,
    )
    bundle = run(
        ContextCompiler(InMemoryContextBundleStore()).compile(
            request=request(scopes=("project",)), sources=(b, a)
        )
    )
    facts = json.loads(bundle.task_context)["pinned_facts"]
    assert facts[0]["source_refs"] == [a.source_ref, b.source_ref]


def test_scope_shape_and_memory_permission_checks_fail_closed():
    scope = ConstraintScopeSnapshot(
        semantic_tags=("logo",),
        region=NormalizedRectSnapshot(x=0.1, y=0.1, width=0.4, height=0.4),
    )
    brand = source(
        "brand",
        ContextSourceType.APPROVED_BRAND_RULE,
        ContextScopeKind.BRAND,
        "brand-a",
        constraints=(
            constraint(
                C1,
                kind="PROTECT_REGION",
                scope=scope,
                parameters={"max_diff": 0.05},
            ),
        ),
    )
    with pytest.raises(ContextSourcePermissionError):
        run(
            ContextCompiler(InMemoryContextBundleStore()).compile(
                request=request(scopes=("project",)), sources=(brand,)
            )
        )
    wrong = replace(brand, scope_id="brand-other", content_hash="")
    wrong = replace(wrong, content_hash=wrong.expected_content_hash())
    with pytest.raises(ContextSourceValidationError, match="SCOPE_MISMATCH"):
        run(
            ContextCompiler(InMemoryContextBundleStore()).compile(
                request=request(), sources=(wrong,)
            )
        )


def test_compile_is_order_independent_content_addressed_and_source_hash_bound():
    project = source(
        "project",
        ContextSourceType.PROJECT_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        fact=ContextFact("product.category", "coffee"),
    )
    task = source(
        "task",
        ContextSourceType.USER_EXPLICIT,
        ContextScopeKind.TASK,
        str(TASK),
        fact=ContextFact("request.locale", "ja-JP", ContextFactChannel.TASK),
        source_text="original explicit request",
    )
    store = InMemoryContextBundleStore()
    compiler = ContextCompiler(store)
    first = run(
        compiler.compile(request=request(scopes=("project",)), sources=(project, task))
    )
    second = run(
        compiler.compile(request=request(scopes=("project",)), sources=(task, project))
    )
    assert first.context_bundle_ref == second.context_bundle_ref
    assert first.content_hash == second.content_hash
    task2 = source(
        "task",
        ContextSourceType.USER_EXPLICIT,
        ContextScopeKind.TASK,
        str(TASK),
        fact=ContextFact("request.locale", "ja-JP", ContextFactChannel.TASK),
        source_text="changed but structured value same",
    )
    third = run(
        compiler.compile(request=request(scopes=("project",)), sources=(project, task2))
    )
    assert third.content_hash != first.content_hash
    payload = json.loads(first.task_context)
    provenance = {
        item["source_ref"]: item["content_hash"]
        for item in payload["source_provenance"]
    }
    assert provenance[task.source_ref] == task.content_hash
    assert "original explicit request" not in first.task_context


def test_provider_returns_exact_pinned_bundle_and_rechecks_identity_permissions():
    project = source(
        "project",
        ContextSourceType.PROJECT_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        fact=ContextFact("project.name", "LUMI"),
    )
    store = InMemoryContextBundleStore()
    compiled = run(
        ContextCompiler(store).compile(
            request=request(scopes=("project",)), sources=(project,)
        )
    )
    provider = ContextBundleProviderAdapter(store)
    pinned = run(
        provider.load(
            context_bundle_ref=compiled.context_bundle_ref,
            context=invocation(scopes=("project",)),
        )
    )
    assert pinned.context_bundle_ref == compiled.context_bundle_ref
    assert pinned.content_hash == compiled.content_hash
    assert pinned.source_refs == (project.source_ref,)
    with pytest.raises(ContextSourcePermissionError, match="PERMISSION_REVOKED"):
        run(
            provider.load(
                context_bundle_ref=compiled.context_bundle_ref,
                context=invocation(scopes=()),
            )
        )
    with pytest.raises(ContextBundleIntegrityError, match="TASK_MISMATCH"):
        run(
            provider.load(
                context_bundle_ref=compiled.context_bundle_ref,
                context=invocation(scopes=("project",), task_id=None),
            )
        )


def test_provider_detects_content_and_permission_metadata_tampering():
    store = InMemoryContextBundleStore()
    project = source(
        "project-meta",
        ContextSourceType.PROJECT_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        fact=ContextFact("project.mode", "production"),
    )
    compiled = run(
        ContextCompiler(store).compile(
            request=request(scopes=("project",)), sources=(project,)
        )
    )
    store._items[compiled.context_bundle_ref] = replace(
        compiled, task_context='{"tampered":true}'
    )
    with pytest.raises(ContextBundleIntegrityError, match="HASH_MISMATCH"):
        run(
            ContextBundleProviderAdapter(store).load(
                context_bundle_ref=compiled.context_bundle_ref,
                context=invocation(scopes=("project",)),
            )
        )

    store._items[compiled.context_bundle_ref] = replace(
        compiled, required_memory_scopes=()
    )
    with pytest.raises(
        ContextBundleIntegrityError,
        match="METADATA_MISMATCH:required_memory_scopes",
    ):
        run(
            ContextBundleProviderAdapter(store).load(
                context_bundle_ref=compiled.context_bundle_ref,
                context=invocation(scopes=()),
            )
        )


def test_git_workspace_store_roundtrip_is_atomic_and_canonical(tmp_path: Path):
    project = source(
        "project",
        ContextSourceType.PROJECT_RULE,
        ContextScopeKind.PROJECT,
        str(PROJECT),
        fact=ContextFact("project.name", "LUMI"),
    )
    store = GitWorkspaceContextBundleStore(tmp_path)
    compiled = run(
        ContextCompiler(store).compile(
            request=request(scopes=("project",)), sources=(project,)
        )
    )
    loaded = run(store.get(compiled.context_bundle_ref))
    assert loaded == compiled
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "context_bundle_ref" in text
