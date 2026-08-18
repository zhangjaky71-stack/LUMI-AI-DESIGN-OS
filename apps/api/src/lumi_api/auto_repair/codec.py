from __future__ import annotations

from decimal import Decimal
from typing import Any

from lumi_auto_repair import (
    AutoRepairJob,
    AutoRepairTaskSpec,
    ConstraintCheck,
    RepairAttempt,
    RepairAttemptDecision,
    RepairCandidate,
    RepairDirective,
    RepairKind,
    RepairLoopStatus,
    RepairPlan,
    RepairPolicySnapshot,
    RepairQualitySnapshot,
    RepairSourceSnapshot,
)


def encode_directive(value: RepairDirective) -> dict[str, Any]:
    return {
        "directive_id": value.directive_id,
        "source_violation_id": value.source_violation_id,
        "dimension": value.dimension,
        "severity": value.severity,
        "blocking": value.blocking,
        "action_type": value.action_type,
        "target": value.target,
        "parameters": value.parameters,
        "protected_refs": list(value.protected_refs),
    }


def decode_directive(value: dict[str, Any]) -> RepairDirective:
    return RepairDirective(
        directive_id=str(value["directive_id"]),
        source_violation_id=str(value["source_violation_id"]),
        dimension=str(value["dimension"]),
        severity=str(value["severity"]),
        blocking=bool(value["blocking"]),
        action_type=str(value["action_type"]),
        target=str(value["target"]),
        parameters=dict(value.get("parameters", {})),
        protected_refs=tuple(
            str(item) for item in value.get("protected_refs", [])
        ),
    )


def encode_quality(value: RepairQualitySnapshot) -> dict[str, Any]:
    return {
        "quality_result_id": value.quality_result_id,
        "artifact_version_id": value.artifact_version_id,
        "status": value.status,
        "overall_score": value.overall_score,
        "overall_confidence": value.overall_confidence,
        "hard_violation_codes": list(value.hard_violation_codes),
        "directives": [encode_directive(item) for item in value.directives],
        "profile_id": value.profile_id,
        "profile_version": value.profile_version,
        "profile_hash": value.profile_hash,
    }


def decode_quality(value: dict[str, Any]) -> RepairQualitySnapshot:
    return RepairQualitySnapshot(
        quality_result_id=str(value["quality_result_id"]),
        artifact_version_id=str(value["artifact_version_id"]),
        status=str(value["status"]),
        overall_score=float(value["overall_score"]),
        overall_confidence=float(value["overall_confidence"]),
        hard_violation_codes=tuple(
            str(item) for item in value.get("hard_violation_codes", [])
        ),
        directives=tuple(
            decode_directive(item) for item in value.get("directives", [])
        ),
        profile_id=str(value["profile_id"]),
        profile_version=int(value["profile_version"]),
        profile_hash=str(value["profile_hash"]),
    )


def encode_source(value: RepairSourceSnapshot) -> dict[str, Any]:
    return {
        "organization_id": value.organization_id,
        "project_id": value.project_id,
        "artifact_id": value.artifact_id,
        "artifact_version_id": value.artifact_version_id,
        "artifact_content_hash": value.artifact_content_hash,
        "artifact_type": value.artifact_type,
        "original_branch_id": value.original_branch_id,
        "original_head_version_id": value.original_head_version_id,
        "design_document_id": value.design_document_id,
        "design_document_version_id": value.design_document_version_id,
        "constraint_snapshot_hash": value.constraint_snapshot_hash,
        "protected_refs": list(value.protected_refs),
    }


def decode_source(value: dict[str, Any]) -> RepairSourceSnapshot:
    return RepairSourceSnapshot(
        organization_id=str(value["organization_id"]),
        project_id=str(value["project_id"]),
        artifact_id=str(value["artifact_id"]),
        artifact_version_id=str(value["artifact_version_id"]),
        artifact_content_hash=str(value["artifact_content_hash"]),
        artifact_type=str(value["artifact_type"]),
        original_branch_id=str(value["original_branch_id"]),
        original_head_version_id=str(value["original_head_version_id"]),
        design_document_id=value.get("design_document_id"),
        design_document_version_id=value.get("design_document_version_id"),
        constraint_snapshot_hash=value.get("constraint_snapshot_hash"),
        protected_refs=tuple(
            str(item) for item in value.get("protected_refs", [])
        ),
    )


def encode_policy(value: RepairPolicySnapshot) -> dict[str, Any]:
    return {
        "policy_id": value.policy_id,
        "version": value.version,
        "max_iterations": value.max_iterations,
        "max_total_cost_usd": str(value.max_total_cost_usd),
        "minimum_expected_gain": value.minimum_expected_gain,
        "max_score_regression": value.max_score_regression,
        "allowed_kinds": sorted(item.value for item in value.allowed_kinds),
        "allow_paid_repairs": value.allow_paid_repairs,
    }


def decode_policy(value: dict[str, Any]) -> RepairPolicySnapshot:
    return RepairPolicySnapshot(
        policy_id=str(value["policy_id"]),
        version=int(value["version"]),
        max_iterations=int(value["max_iterations"]),
        max_total_cost_usd=Decimal(str(value["max_total_cost_usd"])),
        minimum_expected_gain=float(value["minimum_expected_gain"]),
        max_score_regression=float(value["max_score_regression"]),
        allowed_kinds=frozenset(
            RepairKind(str(item)) for item in value["allowed_kinds"]
        ),
        allow_paid_repairs=bool(value["allow_paid_repairs"]),
    )


def encode_plan(value: RepairPlan) -> dict[str, Any]:
    return {
        "iteration": value.iteration,
        "kind": value.kind.value,
        "directives": [encode_directive(item) for item in value.directives],
        "expected_gain": value.expected_gain,
        "estimated_cost_usd": str(value.estimated_cost_usd),
        "paid": value.paid,
        "reason_codes": list(value.reason_codes),
    }


def decode_plan(value: dict[str, Any]) -> RepairPlan:
    return RepairPlan(
        iteration=int(value["iteration"]),
        kind=RepairKind(str(value["kind"])),
        directives=tuple(
            decode_directive(item) for item in value.get("directives", [])
        ),
        expected_gain=float(value["expected_gain"]),
        estimated_cost_usd=Decimal(str(value["estimated_cost_usd"])),
        paid=bool(value["paid"]),
        reason_codes=tuple(
            str(item) for item in value.get("reason_codes", [])
        ),
    )


def encode_check(value: ConstraintCheck | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "passed": value.passed,
        "blocking_codes": list(value.blocking_codes),
        "unavailable": value.unavailable,
        "evidence_refs": list(value.evidence_refs),
    }


def decode_check(value: dict[str, Any] | None) -> ConstraintCheck | None:
    if value is None:
        return None
    return ConstraintCheck(
        passed=bool(value["passed"]),
        blocking_codes=tuple(
            str(item) for item in value.get("blocking_codes", [])
        ),
        unavailable=bool(value.get("unavailable", False)),
        evidence_refs=tuple(
            str(item) for item in value.get("evidence_refs", [])
        ),
    )


def encode_candidate(value: RepairCandidate | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "artifact_version_id": value.artifact_version_id,
        "artifact_content_hash": value.artifact_content_hash,
        "repair_branch_id": value.repair_branch_id,
        "changed_node_ids": list(value.changed_node_ids),
        "actual_cost_usd": str(value.actual_cost_usd),
        "provider": value.provider,
        "model": value.model,
        "provider_request_id": value.provider_request_id,
        "metadata": value.metadata,
    }


def decode_candidate(value: dict[str, Any] | None) -> RepairCandidate | None:
    if value is None:
        return None
    return RepairCandidate(
        artifact_version_id=str(value["artifact_version_id"]),
        artifact_content_hash=str(value["artifact_content_hash"]),
        repair_branch_id=str(value["repair_branch_id"]),
        changed_node_ids=tuple(
            str(item) for item in value.get("changed_node_ids", [])
        ),
        actual_cost_usd=Decimal(str(value["actual_cost_usd"])),
        provider=value.get("provider"),
        model=value.get("model"),
        provider_request_id=value.get("provider_request_id"),
        metadata=dict(value.get("metadata", {})),
    )


def encode_attempt(value: RepairAttempt) -> dict[str, Any]:
    return {
        "iteration": value.iteration,
        "source_artifact_version_id": value.source_artifact_version_id,
        "before_quality_result_id": value.before_quality_result_id,
        "before_score": value.before_score,
        "plan": encode_plan(value.plan),
        "candidate": encode_candidate(value.candidate),
        "after_quality_result_id": value.after_quality_result_id,
        "after_score": value.after_score,
        "score_delta": value.score_delta,
        "decision": value.decision.value,
        "preflight": encode_check(value.preflight),
        "postflight": encode_check(value.postflight),
        "reservation_id": value.reservation_id,
        "actual_cost_usd": str(value.actual_cost_usd),
        "promoted_artifact_version_id": value.promoted_artifact_version_id,
        "promotion_quality_result_id": value.promotion_quality_result_id,
        "reason_codes": list(value.reason_codes),
    }


def decode_attempt(value: dict[str, Any]) -> RepairAttempt:
    return RepairAttempt(
        iteration=int(value["iteration"]),
        source_artifact_version_id=str(value["source_artifact_version_id"]),
        before_quality_result_id=str(value["before_quality_result_id"]),
        before_score=float(value["before_score"]),
        plan=decode_plan(value["plan"]),
        candidate=decode_candidate(value.get("candidate")),
        after_quality_result_id=value.get("after_quality_result_id"),
        after_score=(
            None
            if value.get("after_score") is None
            else float(value["after_score"])
        ),
        score_delta=(
            None
            if value.get("score_delta") is None
            else float(value["score_delta"])
        ),
        decision=RepairAttemptDecision(str(value["decision"])),
        preflight=decode_check(value.get("preflight")),
        postflight=decode_check(value.get("postflight")),
        reservation_id=value.get("reservation_id"),
        actual_cost_usd=Decimal(str(value.get("actual_cost_usd", "0"))),
        promoted_artifact_version_id=value.get("promoted_artifact_version_id"),
        promotion_quality_result_id=value.get("promotion_quality_result_id"),
        reason_codes=tuple(
            str(item) for item in value.get("reason_codes", [])
        ),
    )


def encode_job(value: AutoRepairJob) -> dict[str, Any]:
    return {
        "job_id": value.job_id,
        "spec": {
            "organization_id": value.spec.organization_id,
            "project_id": value.spec.project_id,
            "task_id": value.spec.task_id,
            "operation_id": value.spec.operation_id,
            "requested_by": value.spec.requested_by,
            "source_artifact_version_id": (
                value.spec.source_artifact_version_id
            ),
            "quality_result_id": value.spec.quality_result_id,
            "policy": encode_policy(value.spec.policy),
        },
        "status": value.status.value,
        "original_source": encode_source(value.original_source),
        "working_source": encode_source(value.working_source),
        "current_quality": encode_quality(value.current_quality),
        "attempts": [encode_attempt(item) for item in value.attempts],
        "spent_usd": str(value.spent_usd),
        "final_artifact_version_id": value.final_artifact_version_id,
        "reason_codes": list(value.reason_codes),
    }


def decode_job(value: dict[str, Any]) -> AutoRepairJob:
    spec_value = value["spec"]
    spec = AutoRepairTaskSpec(
        organization_id=str(spec_value["organization_id"]),
        project_id=str(spec_value["project_id"]),
        task_id=str(spec_value["task_id"]),
        operation_id=str(spec_value["operation_id"]),
        requested_by=str(spec_value["requested_by"]),
        source_artifact_version_id=str(
            spec_value["source_artifact_version_id"]
        ),
        quality_result_id=str(spec_value["quality_result_id"]),
        policy=decode_policy(spec_value["policy"]),
    )
    return AutoRepairJob(
        job_id=str(value["job_id"]),
        spec=spec,
        status=RepairLoopStatus(str(value["status"])),
        original_source=decode_source(value["original_source"]),
        working_source=decode_source(value["working_source"]),
        current_quality=decode_quality(value["current_quality"]),
        attempts=tuple(
            decode_attempt(item) for item in value.get("attempts", [])
        ),
        spent_usd=Decimal(str(value.get("spent_usd", "0"))),
        final_artifact_version_id=value.get("final_artifact_version_id"),
        reason_codes=tuple(
            str(item) for item in value.get("reason_codes", [])
        ),
    )
