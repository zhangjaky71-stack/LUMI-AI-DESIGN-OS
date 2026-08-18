from __future__ import annotations

from datetime import UTC, datetime

from .model import (
    AgentControlEvidence,
    ArtifactObjectEvidence,
    IdempotencyEvidence,
    ObjectVerification,
    RecoveryDecision,
    RecoveryDisposition,
    RecoverySubjectType,
    RuntimeJobEvidence,
)

_TERMINAL_RUNTIME = frozenset({"succeeded", "failed", "cancelled"})
_TERMINAL_OPERATION = frozenset({"succeeded", "failed_final"})


def classify_runtime_job(
    runtime: RuntimeJobEvidence,
    operation: IdempotencyEvidence | None,
    *,
    now: datetime | None = None,
) -> RecoveryDecision:
    current = now or datetime.now(UTC)
    if runtime.status in _TERMINAL_RUNTIME:
        return _decision(
            RecoverySubjectType.RUNTIME_JOB,
            runtime.job_id,
            RecoveryDisposition.TERMINAL,
            "RUNTIME_ALREADY_TERMINAL",
            operation=operation,
        )
    if runtime.status in {"pending", "retrying"}:
        if runtime.attempt_count >= runtime.max_attempts:
            return _decision(
                RecoverySubjectType.RUNTIME_JOB,
                runtime.job_id,
                RecoveryDisposition.REVIEW_REQUIRED,
                "RUNTIME_ATTEMPT_LIMIT_REACHED",
                operation=operation,
            )
        if operation is not None and operation.provider_request_id:
            return _decision(
                RecoverySubjectType.RUNTIME_JOB,
                runtime.job_id,
                RecoveryDisposition.RECONCILE_EXTERNAL,
                "RUNTIME_HAS_EXISTING_PROVIDER_REQUEST",
                operation=operation,
            )
        if operation is not None and operation.paid and operation.status == "in_progress":
            if _lease_active(operation, current):
                return _decision(
                    RecoverySubjectType.RUNTIME_JOB,
                    runtime.job_id,
                    RecoveryDisposition.SKIP,
                    "PAID_OPERATION_LEASE_STILL_ACTIVE",
                    operation=operation,
                )
            return _decision(
                RecoverySubjectType.RUNTIME_JOB,
                runtime.job_id,
                RecoveryDisposition.REVIEW_REQUIRED,
                "PAID_OPERATION_SIDE_EFFECT_AMBIGUOUS",
                operation=operation,
            )
        return _decision(
            RecoverySubjectType.RUNTIME_JOB,
            runtime.job_id,
            RecoveryDisposition.REQUEUE_SAFE,
            "RUNTIME_DB_STATE_REDISPATCHABLE",
            operation=operation,
        )
    if runtime.status == "running":
        if operation is None:
            return _decision(
                RecoverySubjectType.RUNTIME_JOB,
                runtime.job_id,
                RecoveryDisposition.REVIEW_REQUIRED,
                "RUNNING_JOB_HAS_NO_IDEMPOTENCY_EVIDENCE",
            )
        if _lease_active(operation, current):
            return _decision(
                RecoverySubjectType.RUNTIME_JOB,
                runtime.job_id,
                RecoveryDisposition.SKIP,
                "OPERATION_LEASE_STILL_ACTIVE",
                operation=operation,
            )
        if operation.provider_request_id:
            return _decision(
                RecoverySubjectType.RUNTIME_JOB,
                runtime.job_id,
                RecoveryDisposition.RECONCILE_EXTERNAL,
                "RUNNING_JOB_PROVIDER_REQUEST_MUST_BE_RECONCILED",
                operation=operation,
            )
        if operation.paid:
            return _decision(
                RecoverySubjectType.RUNTIME_JOB,
                runtime.job_id,
                RecoveryDisposition.REVIEW_REQUIRED,
                "RUNNING_PAID_SIDE_EFFECT_WITHOUT_PROVIDER_ID",
                operation=operation,
            )
        if operation.status in {"new", "failed_retryable"}:
            return _decision(
                RecoverySubjectType.RUNTIME_JOB,
                runtime.job_id,
                RecoveryDisposition.REQUEUE_SAFE,
                "UNPAID_OPERATION_EXPLICITLY_RETRYABLE",
                operation=operation,
            )
        return _decision(
            RecoverySubjectType.RUNTIME_JOB,
            runtime.job_id,
            RecoveryDisposition.REVIEW_REQUIRED,
            "RUNNING_JOB_OWNERSHIP_AMBIGUOUS",
            operation=operation,
        )
    return _decision(
        RecoverySubjectType.RUNTIME_JOB,
        runtime.job_id,
        RecoveryDisposition.REVIEW_REQUIRED,
        "RUNTIME_STATUS_NOT_RECOVERY_CLASSIFIED",
        operation=operation,
    )


def classify_idempotency_operation(
    operation: IdempotencyEvidence,
    *,
    now: datetime | None = None,
) -> RecoveryDecision:
    current = now or datetime.now(UTC)
    if operation.status in _TERMINAL_OPERATION:
        return _decision(
            RecoverySubjectType.IDEMPOTENCY_OPERATION,
            operation.operation_id,
            RecoveryDisposition.TERMINAL,
            "OPERATION_ALREADY_TERMINAL",
            operation=operation,
        )
    if _lease_active(operation, current):
        return _decision(
            RecoverySubjectType.IDEMPOTENCY_OPERATION,
            operation.operation_id,
            RecoveryDisposition.SKIP,
            "OPERATION_LEASE_STILL_ACTIVE",
            operation=operation,
        )
    if operation.provider_request_id:
        return _decision(
            RecoverySubjectType.IDEMPOTENCY_OPERATION,
            operation.operation_id,
            RecoveryDisposition.RECONCILE_EXTERNAL,
            "EXISTING_PROVIDER_REQUEST_MUST_BE_REUSED",
            operation=operation,
        )
    if operation.paid:
        return _decision(
            RecoverySubjectType.IDEMPOTENCY_OPERATION,
            operation.operation_id,
            RecoveryDisposition.REVIEW_REQUIRED,
            "PAID_SIDE_EFFECT_WITHOUT_NATIVE_REQUEST_ID",
            operation=operation,
        )
    if operation.status in {"new", "failed_retryable"}:
        return _decision(
            RecoverySubjectType.IDEMPOTENCY_OPERATION,
            operation.operation_id,
            RecoveryDisposition.REQUEUE_SAFE,
            "UNPAID_OPERATION_RETRYABLE_WITH_SAME_ID",
            operation=operation,
        )
    return _decision(
        RecoverySubjectType.IDEMPOTENCY_OPERATION,
        operation.operation_id,
        RecoveryDisposition.REVIEW_REQUIRED,
        "IN_PROGRESS_OPERATION_OWNERSHIP_AMBIGUOUS",
        operation=operation,
    )


def classify_agent_control(evidence: AgentControlEvidence) -> RecoveryDecision:
    if evidence.control_status in {"succeeded", "failed", "cancelled"}:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.AGENT_RUN,
            subject_id=str(evidence.agent_run_id),
            disposition=RecoveryDisposition.TERMINAL,
            reason_code="AGENT_RUN_ALREADY_TERMINAL",
        )
    if not evidence.current_graph_enabled:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.AGENT_RUN,
            subject_id=str(evidence.agent_run_id),
            disposition=RecoveryDisposition.REVIEW_REQUIRED,
            reason_code="AGENT_GRAPH_DEFINITION_DISABLED_OR_MISSING",
        )
    if evidence.current_graph_definition_hash != evidence.graph_definition_hash:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.AGENT_RUN,
            subject_id=str(evidence.agent_run_id),
            disposition=RecoveryDisposition.REVIEW_REQUIRED,
            reason_code="AGENT_GRAPH_DEFINITION_HASH_MISMATCH",
        )
    if evidence.control_status == "waiting_user":
        return RecoveryDecision(
            subject_type=RecoverySubjectType.AGENT_RUN,
            subject_id=str(evidence.agent_run_id),
            disposition=RecoveryDisposition.SKIP,
            reason_code="AGENT_WAITING_FOR_USER_MUST_BE_PRESERVED",
        )
    if evidence.control_status == "waiting_external":
        if evidence.checkpoint_id is None:
            return RecoveryDecision(
                subject_type=RecoverySubjectType.AGENT_RUN,
                subject_id=str(evidence.agent_run_id),
                disposition=RecoveryDisposition.REVIEW_REQUIRED,
                reason_code="WAITING_EXTERNAL_WITHOUT_CHECKPOINT",
            )
        return RecoveryDecision(
            subject_type=RecoverySubjectType.AGENT_RUN,
            subject_id=str(evidence.agent_run_id),
            disposition=RecoveryDisposition.RECONCILE_EXTERNAL,
            reason_code="AGENT_EXTERNAL_WAIT_REQUIRES_RECONCILIATION",
        )
    if evidence.control_status in {"running", "cancel_requested"} and evidence.checkpoint_id is None:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.AGENT_RUN,
            subject_id=str(evidence.agent_run_id),
            disposition=RecoveryDisposition.REVIEW_REQUIRED,
            reason_code="AGENT_RUNNING_WITHOUT_DURABLE_CHECKPOINT",
        )
    if evidence.control_status in {"pending", "running", "cancel_requested"}:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.AGENT_RUN,
            subject_id=str(evidence.agent_run_id),
            disposition=RecoveryDisposition.RESUME_SAFE,
            reason_code="AGENT_CHECKPOINT_AND_GRAPH_COMPATIBLE",
        )
    return RecoveryDecision(
        subject_type=RecoverySubjectType.AGENT_RUN,
        subject_id=str(evidence.agent_run_id),
        disposition=RecoveryDisposition.REVIEW_REQUIRED,
        reason_code="AGENT_CONTROL_STATUS_NOT_RECOVERY_CLASSIFIED",
    )


def classify_object_verification(
    expected: ArtifactObjectEvidence,
    measured: ObjectVerification,
) -> RecoveryDecision:
    subject_id = f"{expected.artifact_version_id}:{expected.file_id}"
    if not measured.exists:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.ARTIFACT_FILE,
            subject_id=subject_id,
            disposition=RecoveryDisposition.REVIEW_REQUIRED,
            reason_code="ARTIFACT_OBJECT_MISSING",
            evidence={"bucket": expected.bucket, "storage_key": expected.storage_key},
        )
    if measured.measured_size_bytes is None or measured.measured_checksum_sha256 is None:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.ARTIFACT_FILE,
            subject_id=subject_id,
            disposition=RecoveryDisposition.VERIFY_OBJECT,
            reason_code="ARTIFACT_OBJECT_NEEDS_FULL_VERIFICATION",
        )
    if measured.measured_size_bytes != expected.expected_size_bytes:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.ARTIFACT_FILE,
            subject_id=subject_id,
            disposition=RecoveryDisposition.REVIEW_REQUIRED,
            reason_code="ARTIFACT_OBJECT_SIZE_MISMATCH",
        )
    if measured.measured_checksum_sha256 != expected.expected_checksum_sha256:
        return RecoveryDecision(
            subject_type=RecoverySubjectType.ARTIFACT_FILE,
            subject_id=subject_id,
            disposition=RecoveryDisposition.REVIEW_REQUIRED,
            reason_code="ARTIFACT_OBJECT_CHECKSUM_MISMATCH",
        )
    return RecoveryDecision(
        subject_type=RecoverySubjectType.ARTIFACT_FILE,
        subject_id=subject_id,
        disposition=RecoveryDisposition.TERMINAL,
        reason_code="ARTIFACT_OBJECT_VERIFIED",
    )


def _lease_active(operation: IdempotencyEvidence, now: datetime) -> bool:
    return operation.lease_expires_at is not None and operation.lease_expires_at > now


def _decision(
    subject_type: RecoverySubjectType,
    subject_id: object,
    disposition: RecoveryDisposition,
    reason: str,
    *,
    operation: IdempotencyEvidence | None = None,
) -> RecoveryDecision:
    return RecoveryDecision(
        subject_type=subject_type,
        subject_id=str(subject_id),
        disposition=disposition,
        reason_code=reason,
        preserve_operation_id=(operation.operation_id if operation is not None else None),
        preserve_provider_request_id=(
            operation.provider_request_id if operation is not None else None
        ),
    )
