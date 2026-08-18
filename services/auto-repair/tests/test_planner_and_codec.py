from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from lumi_auto_repair import (
    AutoRepairJob,
    AutoRepairTaskSpec,
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
from lumi_auto_repair.planner import DeterministicRepairPlanner
from lumi_api.auto_repair.codec import decode_job, encode_job


def _id() -> str:
    return str(uuid4())


def _directive(
    action: str,
    *,
    code: str,
    protected_refs: tuple[str, ...] = (),
) -> RepairDirective:
    return RepairDirective(
        directive_id=_id(),
        source_violation_id=_id(),
        violation_code=code,
        dimension="IDENTITY" if protected_refs else "TYPOGRAPHY",
        severity="ERROR",
        blocking=False,
        action_type=action,
        target=_id(),
        parameters={"text": "fixed"} if action == "REPLACE_TEXT" else {"asset_id": _id()},
        protected_refs=protected_refs,
    )


def _policy() -> RepairPolicySnapshot:
    return RepairPolicySnapshot(
        policy_id="repair-v1",
        version=1,
        max_iterations=3,
        max_total_cost_usd=Decimal("3.00"),
        minimum_expected_gain=1.0,
        max_score_regression=1.0,
        allowed_kinds=frozenset(RepairKind),
    )


def _source() -> RepairSourceSnapshot:
    version_id = _id()
    return RepairSourceSnapshot(
        organization_id=_id(),
        project_id=_id(),
        artifact_id=_id(),
        artifact_version_id=version_id,
        artifact_content_hash="a" * 64,
        artifact_type="DESIGN_DOCUMENT",
        original_branch_id=_id(),
        original_head_version_id=version_id,
        constraint_snapshot_hash="c" * 64,
    )


def _job(directives: tuple[RepairDirective, ...]) -> AutoRepairJob:
    source = _source()
    quality = RepairQualitySnapshot(
        quality_result_id=_id(),
        artifact_version_id=source.artifact_version_id,
        status="FAIL_REPAIRABLE",
        overall_score=50,
        overall_confidence=0.9,
        hard_violation_codes=(),
        directives=directives,
        profile_id="general",
        profile_version=1,
        profile_hash="b" * 64,
    )
    spec = AutoRepairTaskSpec(
        organization_id=source.organization_id,
        project_id=source.project_id,
        task_id=_id(),
        operation_id=_id(),
        requested_by="repair-agent",
        source_artifact_version_id=source.artifact_version_id,
        quality_result_id=quality.quality_result_id,
        policy=_policy(),
    )
    return AutoRepairJob(
        job_id=_id(),
        spec=spec,
        status=RepairLoopStatus.PLANNED,
        original_source=source,
        working_source=source,
        current_quality=quality,
    )


def test_planner_prefers_free_typography_over_paid_region_edit() -> None:
    typo = _directive("REPLACE_TEXT", code="TEXT_OVERFLOW")
    region = _directive("REGENERATE_REGION", code="BACKGROUND_NOISE")
    job = _job((region, typo))
    plan = DeterministicRepairPlanner().plan(spec=job.spec, job=job)
    assert plan.kind is RepairKind.COPY_TYPOGRAPHY_FIX
    assert plan.paid is False
    assert plan.directives == (typo,)


def test_protected_asset_restore_stays_structural_and_free() -> None:
    restore = _directive(
        "REPLACE_ASSET",
        code="PRODUCT_IDENTITY_DRIFT",
        protected_refs=("product:hero",),
    )
    job = _job((restore,))
    plan = DeterministicRepairPlanner().plan(spec=job.spec, job=job)
    assert plan.kind is RepairKind.STRUCTURAL_DESIGN_OP
    assert plan.paid is False


def test_planner_does_not_repeat_identical_failed_directive() -> None:
    directive = _directive("REPLACE_TEXT", code="TEXT_OVERFLOW")
    job = _job((directive,))
    first_plan = DeterministicRepairPlanner().plan(spec=job.spec, job=job)
    attempt = RepairAttempt(
        iteration=1,
        source_artifact_version_id=job.working_source.artifact_version_id,
        before_quality_result_id=job.current_quality.quality_result_id,
        before_score=job.current_quality.overall_score,
        plan=first_plan,
        candidate=None,
        after_quality_result_id=None,
        after_score=None,
        score_delta=None,
        decision=RepairAttemptDecision.EXECUTION_FAILED,
    )
    retry = AutoRepairJob(
        job_id=job.job_id,
        spec=job.spec,
        status=RepairLoopStatus.RUNNING,
        original_source=job.original_source,
        working_source=job.working_source,
        current_quality=job.current_quality,
        attempts=(attempt,),
    )
    second = DeterministicRepairPlanner().plan(spec=retry.spec, job=retry)
    assert second.kind is RepairKind.MANUAL_REVIEW
    assert "REPAIR_NO_UNTRIED_REGISTERED_SAFE_ACTION" in second.reason_codes


def test_job_codec_round_trips_violation_code_and_exact_promotion_audit() -> None:
    directive = _directive("REPLACE_TEXT", code="TEXT_OVERFLOW")
    job = _job((directive,))
    plan = RepairPlan(
        iteration=1,
        kind=RepairKind.COPY_TYPOGRAPHY_FIX,
        directives=(directive,),
        expected_gain=10,
        estimated_cost_usd=Decimal("0"),
        paid=False,
        reason_codes=("TEST",),
    )
    candidate = RepairCandidate(
        artifact_version_id=_id(),
        artifact_content_hash="d" * 64,
        repair_branch_id=_id(),
    )
    attempt = RepairAttempt(
        iteration=1,
        source_artifact_version_id=job.working_source.artifact_version_id,
        before_quality_result_id=job.current_quality.quality_result_id,
        before_score=50,
        plan=plan,
        candidate=candidate,
        after_quality_result_id=_id(),
        after_score=80,
        score_delta=30,
        decision=RepairAttemptDecision.PROMOTED,
        promoted_artifact_version_id=_id(),
        promotion_quality_result_id=_id(),
    )
    ready = AutoRepairJob(
        job_id=job.job_id,
        spec=job.spec,
        status=RepairLoopStatus.READY,
        original_source=job.original_source,
        working_source=job.working_source,
        current_quality=job.current_quality,
        attempts=(attempt,),
        final_artifact_version_id=attempt.promoted_artifact_version_id,
    )
    decoded = decode_job(encode_job(ready))
    assert decoded == ready
    assert decoded.attempts[0].plan.directives[0].violation_code == "TEXT_OVERFLOW"
    assert decoded.attempts[0].promotion_quality_result_id == attempt.promotion_quality_result_id
