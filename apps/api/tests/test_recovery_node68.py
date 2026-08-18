from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lumi_api.recovery import (
    AgentControlEvidence,
    ArtifactObjectEvidence,
    IdempotencyEvidence,
    ObjectVerification,
    RecoveryActionDenied,
    RecoveryDisposition,
    RecoveryDrillMeasurement,
    RecoveryService,
    RuntimeJobEvidence,
    classify_agent_control,
    classify_idempotency_operation,
    classify_object_verification,
    classify_runtime_job,
)

ORG = UUID("11111111-1111-4111-8111-111111111111")
PROJECT = UUID("22222222-2222-4222-8222-222222222222")
JOB = UUID("33333333-3333-4333-8333-333333333333")
OP = UUID("44444444-4444-4444-8444-444444444444")
RUN = UUID("55555555-5555-4555-8555-555555555555")
VERSION = UUID("66666666-6666-4666-8666-666666666666")
FILE = UUID("77777777-7777-4777-8777-777777777777")
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def runtime(*, kind="video.render", status="running", operation_id=OP):
    return RuntimeJobEvidence(
        job_id=JOB,
        organization_id=ORG,
        project_id=PROJECT,
        operation_id=operation_id,
        job_kind=kind,
        status=status,
        attempt_count=1,
        max_attempts=3,
        started_at=NOW - timedelta(minutes=30),
    )


def operation(
    *,
    status="in_progress",
    paid=True,
    provider_request_id=None,
    lease_expires_at=None,
):
    return IdempotencyEvidence(
        operation_id=OP,
        organization_id=ORG,
        operation_type="video.generate",
        status=status,
        paid=paid,
        side_effect_kind="provider_generation",
        compensation_mode="non_compensatable",
        lease_owner="worker-a" if lease_expires_at else None,
        lease_expires_at=lease_expires_at,
        provider_request_id=provider_request_id,
    )


def agent(*, status="running", checkpoint_id="cp-1", current_hash="a" * 64):
    return AgentControlEvidence(
        agent_run_id=RUN,
        organization_id=ORG,
        project_id=PROJECT,
        graph_key="lumi.main",
        graph_version="v7",
        graph_definition_hash="a" * 64,
        control_status=status,
        checkpoint_id=checkpoint_id,
        checkpoint_namespace="default",
        resume_version=4,
        current_graph_definition_hash=current_hash,
        current_graph_enabled=True,
    )


def test_running_paid_job_without_provider_identity_requires_review():
    decision = classify_runtime_job(runtime(), operation(), now=NOW)
    assert decision.disposition is RecoveryDisposition.REVIEW_REQUIRED
    assert decision.reason_code == "RUNNING_PAID_SIDE_EFFECT_WITHOUT_PROVIDER_ID"


def test_known_provider_request_is_reconciled_not_requeued():
    evidence = operation(provider_request_id="provider-job-9")
    decision = classify_runtime_job(runtime(), evidence, now=NOW)
    assert decision.disposition is RecoveryDisposition.RECONCILE_EXTERNAL
    assert decision.preserve_operation_id == OP
    assert decision.preserve_provider_request_id == "provider-job-9"


def test_active_paid_lease_is_not_stolen():
    evidence = operation(lease_expires_at=NOW + timedelta(minutes=5))
    decision = classify_runtime_job(runtime(), evidence, now=NOW)
    assert decision.disposition is RecoveryDisposition.SKIP
    assert decision.reason_code == "OPERATION_LEASE_STILL_ACTIVE"


def test_pending_paid_capable_job_without_idempotency_evidence_is_not_requeued():
    decision = classify_runtime_job(
        runtime(status="pending", operation_id=None),
        None,
        now=NOW,
    )
    assert decision.disposition is RecoveryDisposition.REVIEW_REQUIRED
    assert decision.reason_code == "PAID_CAPABLE_RUNTIME_HAS_NO_IDEMPOTENCY_EVIDENCE"


def test_asset_preview_pending_job_can_be_redispatched_with_same_job_identity():
    decision = classify_runtime_job(
        runtime(kind="asset.preview", status="pending", operation_id=None),
        None,
        now=NOW,
    )
    assert decision.disposition is RecoveryDisposition.REQUEUE_SAFE


def test_paid_retryable_operation_without_provider_request_still_requires_review():
    decision = classify_idempotency_operation(
        operation(status="failed_retryable", paid=True),
        now=NOW,
    )
    assert decision.disposition is RecoveryDisposition.REVIEW_REQUIRED


def test_agent_checkpoint_must_match_exact_graph_definition():
    decision = classify_agent_control(agent(current_hash="b" * 64))
    assert decision.disposition is RecoveryDisposition.REVIEW_REQUIRED
    assert decision.reason_code == "AGENT_GRAPH_DEFINITION_HASH_MISMATCH"


def test_waiting_user_is_preserved_and_not_auto_resumed():
    decision = classify_agent_control(agent(status="waiting_user"))
    assert decision.disposition is RecoveryDisposition.SKIP
    assert decision.reason_code == "AGENT_WAITING_FOR_USER_MUST_BE_PRESERVED"


def test_running_agent_requires_durable_checkpoint():
    decision = classify_agent_control(agent(checkpoint_id=None))
    assert decision.disposition is RecoveryDisposition.REVIEW_REQUIRED
    assert decision.reason_code == "AGENT_RUNNING_WITHOUT_DURABLE_CHECKPOINT"


def test_object_checksum_and_size_are_recovery_truth():
    expected = ArtifactObjectEvidence(
        artifact_version_id=VERSION,
        file_id=FILE,
        bucket="artifacts",
        storage_key="org/project/file.png",
        expected_size_bytes=100,
        expected_checksum_sha256="c" * 64,
    )
    decision = classify_object_verification(
        expected,
        ObjectVerification(
            exists=True,
            measured_size_bytes=100,
            measured_checksum_sha256="d" * 64,
        ),
    )
    assert decision.disposition is RecoveryDisposition.REVIEW_REQUIRED
    assert decision.reason_code == "ARTIFACT_OBJECT_CHECKSUM_MISMATCH"


def test_signed_url_is_never_accepted_as_recovery_object_truth():
    with pytest.raises(ValueError, match="RECOVERY_OBJECT_REF_MUST_BE_INTERNAL"):
        ArtifactObjectEvidence(
            artifact_version_id=VERSION,
            file_id=FILE,
            bucket="artifacts",
            storage_key="https://example.invalid/file?X-Amz-Signature=secret",
            expected_size_bytes=1,
            expected_checksum_sha256="c" * 64,
        )


def test_rpo_rto_targets_are_not_claimed_without_measurement():
    target_only = RecoveryDrillMeasurement(
        scenario="postgres-pitr",
        target_rpo_seconds=300,
        target_rto_seconds=1800,
    )
    assert target_only.has_measured_evidence is False
    assert target_only.target_met is False

    measured = target_only.model_copy(
        update={"measured_data_loss_seconds": 120, "measured_restore_seconds": 900}
    )
    assert measured.has_measured_evidence is True
    assert measured.target_met is True


class EmptyScanner:
    def scan_runtime_jobs(self, *, organization_id):
        return ()

    def resolve_operation(self, *, organization_id, operation_id):
        return None

    def scan_idempotency_operations(self, *, organization_id):
        return ()

    def scan_agent_controls(self, *, organization_id):
        return ()


class Reconciler:
    def __init__(self):
        self.calls = []

    async def reconcile_existing(self, *, operation_id, provider_request_id):
        self.calls.append((operation_id, provider_request_id))


class Redispatch:
    def __init__(self):
        self.calls = []

    async def redispatch(self, *, job_id, operation_id):
        self.calls.append((job_id, operation_id))


def test_execute_external_reconcile_reuses_existing_ids_only():
    async def scenario():
        reconciler = Reconciler()
        service = RecoveryService(
            scanner=EmptyScanner(),
            external_reconcile=reconciler,
        )
        decision = classify_idempotency_operation(
            operation(provider_request_id="provider-job-9"),
            now=NOW,
        )
        await service.execute_decision(decision)
        assert reconciler.calls == [(OP, "provider-job-9")]

    asyncio.run(scenario())


def test_review_decision_cannot_execute_side_effect():
    async def scenario():
        service = RecoveryService(scanner=EmptyScanner(), runtime_redispatch=Redispatch())
        decision = classify_runtime_job(runtime(), operation(), now=NOW)
        with pytest.raises(RecoveryActionDenied):
            await service.execute_decision(decision, runtime_job_id=JOB)

    asyncio.run(scenario())
