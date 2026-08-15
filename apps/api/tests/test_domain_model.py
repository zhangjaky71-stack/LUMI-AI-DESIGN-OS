import ast
from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from lumi_api.domain import (
    AgentRun,
    AgentRunStatus,
    Artifact,
    ArtifactVersion,
    ArtifactVersionStatus,
    Asset,
    Branch,
    Brand,
    Budget,
    CostEntry,
    CostEntryKind,
    DesignDocument,
    Generation,
    GenerationStatus,
    InvariantViolation,
    InvalidTransition,
    MimeType,
    ModelRef,
    Money,
    OperationIdentity,
    Project,
    ProjectStatus,
    RightsLevel,
    RightsPolicy,
    StorageRef,
    Task,
    TaskStatus,
    Usage,
    Workspace,
    new_uuid7,
    require_artifact_lineage_acyclic,
    require_same_organization,
    require_task_graph_acyclic,
)


def uid(seed: int) -> UUID:
    return UUID(int=seed)


def test_uuid7_has_rfc_version_variant_and_time_ordering() -> None:
    older = new_uuid7(unix_ms=1_700_000_000_000)
    newer = new_uuid7(unix_ms=1_700_000_000_001)

    assert older.version == 7
    assert newer.version == 7
    assert older.variant == "specified in RFC 4122"
    assert older.int < newer.int


def test_money_requires_decimal_and_prevents_currency_mixing() -> None:
    assert Money(Decimal("1.25"), "usd") == Money(Decimal("1.25"), "USD")
    with pytest.raises(TypeError):
        Money(1.25, "USD")  # type: ignore[arg-type]
    with pytest.raises(InvariantViolation):
        _ = Money(Decimal("1"), "USD") + Money(Decimal("2"), "JPY")


def test_project_state_machine_is_explicit_and_immutable() -> None:
    project = Project(organization_id=uid(1), workspace_id=uid(2), name="Campaign")
    active = project.transition(ProjectStatus.ACTIVE)
    paused = active.transition(ProjectStatus.PAUSED)
    resumed = paused.transition(ProjectStatus.ACTIVE)
    archived = resumed.transition(ProjectStatus.ARCHIVED)

    assert project.status is ProjectStatus.DRAFT
    assert archived.status is ProjectStatus.ARCHIVED
    with pytest.raises(InvalidTransition):
        archived.transition(ProjectStatus.ACTIVE)


def test_agent_run_and_task_state_machines_cover_wait_cancel_and_success() -> None:
    budget = Budget(Money(Decimal("100"), "USD"), Money(Decimal("80"), "USD"))
    run = AgentRun(
        organization_id=uid(1),
        project_id=uid(2),
        thread_id="thread-1",
        graph_version="graph-v1",
        agent_config_version="config-v1",
        budget=budget,
        usage=Usage(),
    )
    waiting = run.transition(AgentRunStatus.RUNNING).transition(AgentRunStatus.WAITING_USER)
    succeeded = waiting.transition(AgentRunStatus.RUNNING).transition(AgentRunStatus.SUCCEEDED)
    assert succeeded.status is AgentRunStatus.SUCCEEDED
    with pytest.raises(InvalidTransition):
        succeeded.transition(AgentRunStatus.RUNNING)

    task = Task(organization_id=uid(1), project_id=uid(2), name="Generate variants")
    done = task.transition(TaskStatus.READY).transition(TaskStatus.RUNNING).transition(
        TaskStatus.SUCCEEDED
    )
    assert done.status is TaskStatus.SUCCEEDED


def test_artifact_approved_version_cannot_be_overwritten_in_place() -> None:
    version = ArtifactVersion(
        organization_id=uid(1),
        artifact_id=uid(2),
        branch_id=uid(3),
        ordinal=1,
        payload_ref="artifact://v1",
    )
    approved = version.transition(ArtifactVersionStatus.READY).transition(
        ArtifactVersionStatus.APPROVED
    )

    with pytest.raises(InvalidTransition):
        approved.transition(ArtifactVersionStatus.REJECTED)
    with pytest.raises(FrozenInstanceError):
        approved.payload_ref = "artifact://tampered"  # type: ignore[misc]


def test_asset_storage_ownership_is_tenant_scoped() -> None:
    storage = StorageRef(
        bucket="assets",
        key="org/1/input.png",
        checksum_sha256="a" * 64,
        owner_organization_id=uid(1),
    )
    rights = RightsPolicy(RightsLevel.OWNED, commercial_use=True)
    asset = Asset(
        organization_id=uid(1),
        storage=storage,
        mime_type=MimeType("image/png"),
        source="upload",
        rights=rights,
    )
    assert asset.storage.owner_organization_id == asset.organization_id

    with pytest.raises(InvariantViolation):
        Asset(
            organization_id=uid(9),
            storage=storage,
            mime_type=MimeType("image/png"),
            source="upload",
            rights=rights,
        )


def test_cross_tenant_relationships_are_rejected() -> None:
    project_a = Project(organization_id=uid(1), workspace_id=uid(11), name="A")
    project_b = Project(organization_id=uid(2), workspace_id=uid(22), name="B")
    task_a = Task(organization_id=uid(1), project_id=project_a.id, name="A task")

    assert require_same_organization(project_a, task_a) == uid(1)
    with pytest.raises(InvariantViolation):
        require_same_organization(project_a, project_b)


def test_task_dependency_graph_rejects_cycles() -> None:
    a, b, c = uid(101), uid(102), uid(103)
    require_task_graph_acyclic({a: (b,), b: (c,), c: ()})

    with pytest.raises(InvariantViolation, match="task dependency graph"):
        require_task_graph_acyclic({a: (b,), b: (c,), c: (a,)})


def test_artifact_lineage_rejects_cycles() -> None:
    v1, v2, v3 = uid(201), uid(202), uid(203)
    require_artifact_lineage_acyclic({v3: (v2,), v2: (v1,), v1: ()})

    with pytest.raises(InvariantViolation, match="artifact lineage"):
        require_artifact_lineage_acyclic({v1: (v3,), v2: (v1,), v3: (v2,)})


def test_cost_ledger_is_append_only_by_value_and_adjustments_reference_prior_entry() -> None:
    charge = CostEntry(
        organization_id=uid(1),
        amount=Money(Decimal("2.50"), "USD"),
        operation_id=uid(300),
    )
    adjustment = CostEntry(
        organization_id=uid(1),
        amount=Money(Decimal("-0.50"), "USD"),
        operation_id=uid(301),
        kind=CostEntryKind.ADJUSTMENT,
        related_entry_id=charge.id,
    )
    assert adjustment.related_entry_id == charge.id

    with pytest.raises(FrozenInstanceError):
        charge.amount = Money(Decimal("999"), "USD")  # type: ignore[misc]
    with pytest.raises(InvariantViolation):
        CostEntry(
            organization_id=uid(1),
            amount=Money(Decimal("-2.50"), "USD"),
            operation_id=uid(302),
            kind=CostEntryKind.REVERSAL,
        )


def test_generation_uses_domain_status_not_provider_error_strings() -> None:
    generation = Generation(
        organization_id=uid(1),
        project_id=uid(2),
        operation=OperationIdentity(uid(3), "generate:project-2:request-1"),
        model=ModelRef("openai", "image-model", "v1"),
    )
    completed = generation.transition(GenerationStatus.RUNNING).transition(
        GenerationStatus.COMPLETED
    )
    assert completed.status is GenerationStatus.COMPLETED
    with pytest.raises(InvalidTransition):
        completed.transition(GenerationStatus.FAILED)


def test_every_tenant_owned_p0_entity_exposes_organization_id() -> None:
    tenant_types = (
        Workspace,
        Project,
        Brand,
        Asset,
        DesignDocument,
        Branch,
        Artifact,
        ArtifactVersion,
        AgentRun,
        Task,
        Generation,
        CostEntry,
    )
    for entity_type in tenant_types:
        assert "organization_id" in {item.name for item in fields(entity_type)}


def test_domain_package_has_no_framework_or_provider_sdk_imports() -> None:
    domain_root = Path(__file__).parents[1] / "src" / "lumi_api" / "domain"
    forbidden = {
        "fastapi",
        "sqlalchemy",
        "pydantic",
        "langgraph",
        "langchain",
        "openai",
        "anthropic",
        "boto3",
    }
    discovered: set[str] = set()

    for path in domain_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                discovered.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                discovered.add(node.module.split(".")[0])

    assert discovered.isdisjoint(forbidden)
