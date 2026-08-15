from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lumi_api.recovery import (
    AgentRunRecoverySnapshot,
    OperationRecoverySnapshot,
    OutboxRecoverySnapshot,
    RecoveryAction,
    TaskRecoverySnapshot,
    plan_agent_run_recovery,
    plan_operation_recovery,
    plan_outbox_recovery,
    plan_task_recovery,
)

NOW = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


def test_ambiguous_paid_operation_is_never_auto_retried() -> None:
    decision = plan_operation_recovery(
        OperationRecoverySnapshot(
            status="ambiguous",
            provider_request_id="provider-123",
            ambiguity_reason="local process died after send",
        ),
        now=NOW,
    )
    assert decision.action is RecoveryAction.MANUAL_REVIEW
    assert decision.automatic is False
    assert decision.stop_auto_retry is True


def test_in_progress_provider_operation_requires_external_reconciliation() -> None:
    decision = plan_operation_recovery(
        OperationRecoverySnapshot(
            status="in_progress",
            provider_request_id="provider-123",
            lease_expires_at=NOW - timedelta(minutes=10),
        ),
        now=NOW,
    )
    assert decision.action is RecoveryAction.RECONCILE_EXTERNAL
    assert decision.stop_auto_retry is True


def test_new_operation_without_provider_request_is_safe_to_requeue() -> None:
    decision = plan_operation_recovery(OperationRecoverySnapshot(status="new"), now=NOW)
    assert decision.action is RecoveryAction.SAFE_REQUEUE
    assert decision.automatic is True


def test_expired_in_progress_operation_without_provider_proof_is_manual() -> None:
    decision = plan_operation_recovery(
        OperationRecoverySnapshot(
            status="in_progress",
            lease_expires_at=NOW - timedelta(seconds=1),
        ),
        now=NOW,
    )
    assert decision.action is RecoveryAction.MANUAL_REVIEW
    assert decision.stop_auto_retry is True


def test_waiting_user_task_is_preserved() -> None:
    decision = plan_task_recovery(
        TaskRecoverySnapshot(status="running", wait_reason="approval"),
        now=NOW,
    )
    assert decision.action is RecoveryAction.PRESERVE_WAIT


def test_external_task_is_not_blindly_requeued() -> None:
    decision = plan_task_recovery(
        TaskRecoverySnapshot(status="running", external_ref="job/provider/42"),
        now=NOW,
    )
    assert decision.action is RecoveryAction.RECONCILE_EXTERNAL
    assert decision.stop_auto_retry is True


def test_expired_local_task_lease_can_be_requeued() -> None:
    decision = plan_task_recovery(
        TaskRecoverySnapshot(
            status="running",
            lease_expires_at=NOW - timedelta(minutes=1),
        ),
        now=NOW,
    )
    assert decision.action is RecoveryAction.SAFE_REQUEUE


def test_task_with_ambiguous_paid_operation_stops_auto_retry() -> None:
    decision = plan_task_recovery(
        TaskRecoverySnapshot(
            status="pending",
            paid_operation_status="ambiguous",
        ),
        now=NOW,
    )
    assert decision.action is RecoveryAction.MANUAL_REVIEW
    assert decision.stop_auto_retry is True


def test_interrupted_agent_run_resumes_only_with_checkpoint() -> None:
    resumable = plan_agent_run_recovery(
        AgentRunRecoverySnapshot(control_status="interrupted", checkpoint_id="cp-7"),
        now=NOW,
    )
    manual = plan_agent_run_recovery(
        AgentRunRecoverySnapshot(control_status="interrupted", checkpoint_id=None),
        now=NOW,
    )
    assert resumable.action is RecoveryAction.RESUME_CHECKPOINT
    assert manual.action is RecoveryAction.MANUAL_REVIEW


def test_stale_agent_run_with_external_side_effect_reconciles_first() -> None:
    decision = plan_agent_run_recovery(
        AgentRunRecoverySnapshot(
            control_status="running",
            checkpoint_id="cp-7",
            updated_at=NOW - timedelta(hours=1),
            has_external_pending_operation=True,
        ),
        now=NOW,
    )
    assert decision.action is RecoveryAction.RECONCILE_EXTERNAL
    assert decision.stop_auto_retry is True


def test_unpublished_outbox_is_replayed_and_published_event_can_be_replayed_in_broker_rebuild() -> None:
    unpublished = plan_outbox_recovery(
        OutboxRecoverySnapshot(event_id="event-1", published_at=None),
    )
    published = plan_outbox_recovery(
        OutboxRecoverySnapshot(event_id="event-2", published_at=NOW),
        broker_rebuild_mode=True,
    )
    assert unpublished.action is RecoveryAction.REPLAY_EVENT
    assert published.action is RecoveryAction.REPLAY_EVENT
    assert "same event id" in published.reason


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        plan_operation_recovery(
            OperationRecoverySnapshot(
                status="in_progress",
                lease_expires_at=datetime(2026, 8, 15, 9, 0),
            ),
            now=NOW,
        )
