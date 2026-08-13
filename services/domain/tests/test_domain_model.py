from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from lumi_domain import (
    AgentRun,
    AgentRunStatus,
    ArtifactVersion,
    ArtifactVersionStatus,
    Asset,
    CostEntry,
    Generation,
    InvalidTransition,
    InvariantViolation,
    Money,
    OperationIdentity,
    Project,
    ProjectStatus,
    ProviderErrorCode,
    RightsPolicy,
    RightsScope,
    StorageRef,
    Task,
    TaskStatus,
    new_uuid7,
    normalize_provider_error,
    uuid7_timestamp_ms,
)
from lumi_domain.invariants import (
    assert_artifact_lineage_acyclic,
    assert_task_graph_acyclic,
    require_hard_constraint_override,
    require_paid_operation_identity,
    require_tenant_membership,
)


def test_uuid7_is_sortable_and_exposes_timestamp() -> None:
    first = new_uuid7(unix_ms=1_700_000_000_000)
    second = new_uuid7(unix_ms=1_700_000_000_001)
    assert first.version == 7
    assert second.version == 7
    assert first.int < second.int
    assert uuid7_timestamp_ms(first) == 1_700_000_000_000


def test_money_requires_decimal_and_normalizes_currency() -> None:
    assert Money(Decimal("12.30"), "usd").currency == "USD"
    with pytest.raises(TypeError):
        Money(12.30, "USD")  # type: ignore[arg-type]


def test_project_state_machine_accepts_only_declared_transitions() -> None:
    project = Project(new_uuid7(), new_uuid7(), "Launch")
    project.transition_to(ProjectStatus.ACTIVE)
    project.transition_to(ProjectStatus.PAUSED)
    project.transition_to(ProjectStatus.ACTIVE)
    project.transition_to(ProjectStatus.ARCHIVED)
    with pytest.raises(InvalidTransition):
        project.transition_to(ProjectStatus.ACTIVE)


def test_agent_run_waiting_user_resume_and_cancel_flow() -> None:
    run = AgentRun(new_uuid7(), new_uuid7(), "thread-1", "graph-v1", "agent-v1")
    run.transition_to(AgentRunStatus.RUNNING)
    run.transition_to(AgentRunStatus.WAITING_USER)
    run.transition_to(AgentRunStatus.RUNNING)
    run.transition_to(AgentRunStatus.CANCEL_REQUESTED)
    run.transition_to(AgentRunStatus.CANCELLED)
    with pytest.raises(InvalidTransition):
        run.transition_to(AgentRunStatus.RUNNING)


def test_task_dependency_wait_and_retry_flow() -> None:
    task = Task(new_uuid7(), new_uuid7(), "render")
    task.transition_to(TaskStatus.READY)
    task.transition_to(TaskStatus.RUNNING)
    task.transition_to(TaskStatus.WAITING_DEPENDENCY)
    task.transition_to(TaskStatus.READY)
    task.transition_to(TaskStatus.RUNNING)
    task.transition_to(TaskStatus.FAILED)
    task.transition_to(TaskStatus.READY)


def test_approved_artifact_version_cannot_be_mutated_or_revised() -> None:
    version = ArtifactVersion(new_uuid7(), new_uuid7(), "sha256:abc")
    version.transition_to(ArtifactVersionStatus.READY)
    version.transition_to(ArtifactVersionStatus.APPROVED)
    with pytest.raises(InvariantViolation):
        version.revised(content_hash="sha256:def")
    with pytest.raises(InvalidTransition):
        version.transition_to(ArtifactVersionStatus.REJECTED)


def test_artifact_lineage_cycle_is_rejected() -> None:
    one, two, three = new_uuid7(), new_uuid7(), new_uuid7()
    with pytest.raises(InvariantViolation, match="artifact lineage"):
        assert_artifact_lineage_acyclic({one: (two,), two: (three,), three: (one,)})
    assert_artifact_lineage_acyclic({one: (two,), two: (three,), three: ()})


def test_task_graph_cycle_is_rejected() -> None:
    one, two = new_uuid7(), new_uuid7()
    with pytest.raises(InvariantViolation, match="task dependency"):
        assert_task_graph_acyclic({one: (two,), two: (one,)})


def test_asset_storage_owner_must_match_tenant() -> None:
    organization_id = new_uuid7()
    storage = StorageRef(
        bucket="assets",
        key="a.png",
        checksum="sha256:" + "a" * 64,
        owner_organization_id=new_uuid7(),
    )
    with pytest.raises(InvariantViolation, match="storage owner"):
        Asset(
            organization_id,
            storage,
            RightsPolicy(RightsScope.COMMERCIAL, source="user-upload"),
        )


def test_storage_reference_requires_checksum() -> None:
    with pytest.raises(ValueError, match="sha256"):
        StorageRef("assets", "a.png", "missing-checksum", new_uuid7())


def test_tenant_membership_is_required_before_access() -> None:
    organization_id = new_uuid7()
    require_tenant_membership(
        object_organization_id=organization_id,
        member_organization_ids=(organization_id,),
    )
    with pytest.raises(InvariantViolation, match="tenant membership"):
        require_tenant_membership(
            object_organization_id=organization_id,
            member_organization_ids=(new_uuid7(),),
        )


def test_hard_constraint_requires_override_audit() -> None:
    with pytest.raises(InvariantViolation, match="audited override"):
        require_hard_constraint_override(violated=True, override_audit_id=None)
    require_hard_constraint_override(violated=True, override_audit_id=new_uuid7())


def test_paid_side_effect_requires_operation_identity() -> None:
    with pytest.raises(InvariantViolation, match="operation/idempotency"):
        require_paid_operation_identity(paid=True, operation=None)
    operation = OperationIdentity(new_uuid7(), "generation:abc")
    require_paid_operation_identity(paid=True, operation=operation)
    Generation(new_uuid7(), new_uuid7(), "openai", "image-model", True, operation)


def test_generation_enforces_paid_operation_identity_itself() -> None:
    with pytest.raises(InvariantViolation, match="operation/idempotency"):
        Generation(new_uuid7(), new_uuid7(), "provider", "model", True, None)


def test_cost_entry_is_immutable_and_adjustments_are_new_ledger_entries() -> None:
    original = CostEntry(new_uuid7(), Money(Decimal("10.00"), "USD"), "provider_cost")
    with pytest.raises(FrozenInstanceError):
        setattr(original, "category", "mutated")
    reversal = original.reversal(reason="provider refund")
    assert reversal.id != original.id
    assert reversal.reverses_entry_id == original.id
    assert reversal.amount.amount == Decimal("-10.00")
    adjustment = original.adjustment(amount=Decimal("2.50"), reason="reconcile")
    assert adjustment.id != original.id
    assert adjustment.amount.amount == Decimal("2.50")


def test_provider_errors_are_normalized_without_provider_sdk_types() -> None:
    rate_limited = normalize_provider_error(
        provider="example",
        status_code=429,
        provider_code="rate_limit_exceeded",
    )
    assert rate_limited.code is ProviderErrorCode.RATE_LIMITED
    assert rate_limited.retryable is True

    safety = normalize_provider_error(provider="example", provider_code="content_filter")
    assert safety.code is ProviderErrorCode.SAFETY_BLOCK
    assert safety.retryable is False

    unavailable = normalize_provider_error(provider="example", status_code=503)
    assert unavailable.code is ProviderErrorCode.UNAVAILABLE
    assert unavailable.retryable is True


def test_domain_package_has_no_framework_or_provider_sdk_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "lumi_domain"
    forbidden = (
        "sqlalchemy",
        "fastapi",
        "httpx",
        "langchain",
        "langgraph",
        "openai",
        "anthropic",
        "google.genai",
        "boto3",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for module in forbidden:
        assert f"import {module}" not in source
        assert f"from {module}" not in source
