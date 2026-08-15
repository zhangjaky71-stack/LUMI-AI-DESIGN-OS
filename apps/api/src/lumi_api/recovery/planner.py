from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class RecoveryAction(StrEnum):
    NO_ACTION = "no_action"
    SAFE_REQUEUE = "safe_requeue"
    REPLAY_EVENT = "replay_event"
    RECONCILE_EXTERNAL = "reconcile_external"
    RESUME_CHECKPOINT = "resume_checkpoint"
    PRESERVE_WAIT = "preserve_wait"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    automatic: bool
    stop_auto_retry: bool = False


@dataclass(frozen=True, slots=True)
class OperationRecoverySnapshot:
    status: str
    provider_request_id: str | None = None
    lease_expires_at: datetime | None = None
    ambiguity_reason: str | None = None


@dataclass(frozen=True, slots=True)
class TaskRecoverySnapshot:
    status: str
    lease_expires_at: datetime | None = None
    external_ref: str | None = None
    wait_reason: str | None = None
    paid_operation_status: str | None = None
    provider_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentRunRecoverySnapshot:
    control_status: str
    checkpoint_id: str | None = None
    updated_at: datetime | None = None
    has_ambiguous_operation: bool = False
    has_external_pending_operation: bool = False


@dataclass(frozen=True, slots=True)
class OutboxRecoverySnapshot:
    event_id: str
    published_at: datetime | None
    publish_attempts: int = 0


def plan_operation_recovery(
    snapshot: OperationRecoverySnapshot,
    *,
    now: datetime | None = None,
) -> RecoveryDecision:
    """Classify one idempotency operation without mutating business state.

    Paid/provider operations are fail-closed: once a provider request may have been
    sent, automatic retry is forbidden until the native provider state is reconciled.
    """
    current = _utc(now)
    status = snapshot.status.strip().lower()

    if status in {"succeeded", "failed_final"}:
        return _decision(RecoveryAction.NO_ACTION, f"operation is terminal: {status}")
    if status == "ambiguous":
        return _decision(
            RecoveryAction.MANUAL_REVIEW,
            snapshot.ambiguity_reason or "operation is explicitly ambiguous",
            automatic=False,
            stop_auto_retry=True,
        )
    if status in {"new", "failed_retryable"}:
        if snapshot.provider_request_id:
            return _decision(
                RecoveryAction.RECONCILE_EXTERNAL,
                "provider request exists; reconcile before any retry",
                automatic=False,
                stop_auto_retry=True,
            )
        return _decision(RecoveryAction.SAFE_REQUEUE, f"operation is safe to retry: {status}")
    if status == "in_progress":
        if snapshot.provider_request_id:
            return _decision(
                RecoveryAction.RECONCILE_EXTERNAL,
                "in-progress operation has provider_request_id",
                automatic=False,
                stop_auto_retry=True,
            )
        if snapshot.lease_expires_at is None:
            return _decision(
                RecoveryAction.MANUAL_REVIEW,
                "in-progress operation has no lease expiry or provider proof",
                automatic=False,
                stop_auto_retry=True,
            )
        if _utc(snapshot.lease_expires_at) > current:
            return _decision(RecoveryAction.NO_ACTION, "operation lease is still active")
        return _decision(
            RecoveryAction.MANUAL_REVIEW,
            "expired in-progress operation cannot prove provider side effect was never sent",
            automatic=False,
            stop_auto_retry=True,
        )
    return _decision(
        RecoveryAction.MANUAL_REVIEW,
        f"unknown operation status: {status or '<empty>'}",
        automatic=False,
        stop_auto_retry=True,
    )


def plan_task_recovery(
    snapshot: TaskRecoverySnapshot,
    *,
    now: datetime | None = None,
) -> RecoveryDecision:
    current = _utc(now)
    status = snapshot.status.strip().lower()
    wait_reason = (snapshot.wait_reason or "").strip().lower()
    paid_status = (snapshot.paid_operation_status or "").strip().lower()

    if status in {"succeeded", "failed", "cancelled", "skipped"}:
        return _decision(RecoveryAction.NO_ACTION, f"task is terminal: {status}")
    if status in {"waiting_user", "waiting_for_user", "interrupted"} or wait_reason in {
        "waiting_user",
        "waiting_for_user",
        "approval",
    }:
        return _decision(RecoveryAction.PRESERVE_WAIT, "task requires user/approval input")
    if snapshot.external_ref or snapshot.provider_request_id or status in {
        "waiting_external",
        "waiting_for_external",
    }:
        return _decision(
            RecoveryAction.RECONCILE_EXTERNAL,
            "task references external/provider state",
            automatic=False,
            stop_auto_retry=True,
        )
    if paid_status == "ambiguous":
        return _decision(
            RecoveryAction.MANUAL_REVIEW,
            "task is linked to an ambiguous paid operation",
            automatic=False,
            stop_auto_retry=True,
        )
    if paid_status == "in_progress":
        return _decision(
            RecoveryAction.MANUAL_REVIEW,
            "task is linked to an in-progress paid operation without external proof",
            automatic=False,
            stop_auto_retry=True,
        )
    if status in {"pending", "ready", "retry", "failed_retryable"}:
        return _decision(RecoveryAction.SAFE_REQUEUE, f"task can be scheduled from DB state: {status}")
    if status == "running":
        if snapshot.lease_expires_at is None:
            return _decision(
                RecoveryAction.MANUAL_REVIEW,
                "running task has no lease expiry",
                automatic=False,
            )
        if _utc(snapshot.lease_expires_at) > current:
            return _decision(RecoveryAction.NO_ACTION, "task lease is still active")
        return _decision(RecoveryAction.SAFE_REQUEUE, "task lease expired with no external/paid side effect")
    return _decision(
        RecoveryAction.MANUAL_REVIEW,
        f"unknown task status: {status or '<empty>'}",
        automatic=False,
    )


def plan_agent_run_recovery(
    snapshot: AgentRunRecoverySnapshot,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 300,
) -> RecoveryDecision:
    current = _utc(now)
    status = snapshot.control_status.strip().lower()

    if status in {"succeeded", "failed", "cancelled"}:
        return _decision(RecoveryAction.NO_ACTION, f"agent run is terminal: {status}")
    if snapshot.has_ambiguous_operation:
        return _decision(
            RecoveryAction.MANUAL_REVIEW,
            "agent run contains an ambiguous side effect",
            automatic=False,
            stop_auto_retry=True,
        )
    if snapshot.has_external_pending_operation:
        return _decision(
            RecoveryAction.RECONCILE_EXTERNAL,
            "agent run has external/provider work that must be reconciled",
            automatic=False,
            stop_auto_retry=True,
        )
    if status == "interrupted":
        if snapshot.checkpoint_id:
            return _decision(RecoveryAction.RESUME_CHECKPOINT, "interrupted run has durable checkpoint")
        return _decision(
            RecoveryAction.MANUAL_REVIEW,
            "interrupted run has no checkpoint",
            automatic=False,
        )
    if status == "pending":
        return _decision(RecoveryAction.SAFE_REQUEUE, "pending run can be started from DB state")
    if status == "running":
        if snapshot.updated_at is None:
            return _decision(
                RecoveryAction.MANUAL_REVIEW,
                "running run has no freshness timestamp",
                automatic=False,
            )
        age = (current - _utc(snapshot.updated_at)).total_seconds()
        if age <= stale_after_seconds:
            return _decision(RecoveryAction.NO_ACTION, "agent run is not stale")
        if snapshot.checkpoint_id:
            return _decision(RecoveryAction.RESUME_CHECKPOINT, "stale run has durable checkpoint")
        return _decision(
            RecoveryAction.MANUAL_REVIEW,
            "stale run has no checkpoint",
            automatic=False,
        )
    return _decision(
        RecoveryAction.MANUAL_REVIEW,
        f"unknown agent control status: {status or '<empty>'}",
        automatic=False,
    )


def plan_outbox_recovery(
    snapshot: OutboxRecoverySnapshot,
    *,
    broker_rebuild_mode: bool = False,
) -> RecoveryDecision:
    if snapshot.publish_attempts < 0:
        return _decision(
            RecoveryAction.MANUAL_REVIEW,
            "outbox publish_attempts is invalid",
            automatic=False,
        )
    if snapshot.published_at is None:
        return _decision(
            RecoveryAction.REPLAY_EVENT,
            "unpublished outbox event is authoritative replay work",
        )
    if broker_rebuild_mode:
        return _decision(
            RecoveryAction.REPLAY_EVENT,
            "replay published event with the same event id; inbox dedupe protects consumers",
        )
    return _decision(RecoveryAction.NO_ACTION, "event is already published")


def _decision(
    action: RecoveryAction,
    reason: str,
    *,
    automatic: bool = True,
    stop_auto_retry: bool = False,
) -> RecoveryDecision:
    return RecoveryDecision(
        action=action,
        reason=reason,
        automatic=automatic,
        stop_auto_retry=stop_auto_retry,
    )


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("recovery timestamps must be timezone-aware")
    return value.astimezone(UTC)
