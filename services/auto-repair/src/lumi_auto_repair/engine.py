from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from .costing import RepairCostEstimate
from .model import (
    AutoRepairJob,
    AutoRepairTaskSpec,
    BudgetReservation,
    ConstraintCheck,
    RepairAttempt,
    RepairAttemptDecision,
    RepairCandidate,
    RepairKind,
    RepairLoopStatus,
    RepairPlan,
    RepairQualitySnapshot,
)
from .planner import DeterministicRepairPlanner
from .ports import (
    AutoRepairRepositoryPort,
    RepairArtifactPort,
    RepairBudgetPort,
    RepairConstraintPort,
    RepairExecutorPort,
    RepairPlannerPort,
    RepairQualityPort,
)


class AutoRepairOperationConflict(RuntimeError):
    pass


class RepairStaleConflict(RuntimeError):
    pass


class RepairSideEffectUncertain(RuntimeError):
    """A paid call may have started and must be reconciled, never replayed blindly."""

    def __init__(self, message: str, *, external_operation_id: str | None = None) -> None:
        super().__init__(message)
        self.external_operation_id = external_operation_id


_TERMINAL = {
    RepairLoopStatus.READY,
    RepairLoopStatus.REVIEW_REQUIRED,
    RepairLoopStatus.FAILED,
    RepairLoopStatus.BUDGET_EXHAUSTED,
    RepairLoopStatus.STALE_CONFLICT,
    RepairLoopStatus.CANCELLED,
}
_PASS_QUALITY = {"PASS", "PASS_WITH_WARNINGS"}
_REPAIRABLE_QUALITY = {"FAIL_REPAIRABLE", "FAIL_HARD"}


class AutoRepairEngine:
    """Bounded NODE-51 orchestration; each resume executes at most one repair."""

    def __init__(
        self,
        *,
        artifacts: RepairArtifactPort,
        quality: RepairQualityPort,
        constraints: RepairConstraintPort,
        executor: RepairExecutorPort,
        budget: RepairBudgetPort,
        repository: AutoRepairRepositoryPort,
        planner: RepairPlannerPort | None = None,
    ) -> None:
        self.artifacts = artifacts
        self.quality = quality
        self.constraints = constraints
        self.executor = executor
        self.budget = budget
        self.repository = repository
        self.planner = planner or DeterministicRepairPlanner()

    def start(self, spec: AutoRepairTaskSpec) -> AutoRepairJob:
        existing = self.repository.get_by_operation(
            organization_id=spec.organization_id,
            operation_id=spec.operation_id,
        )
        if existing is not None:
            if existing.spec.semantic_hash() != spec.semantic_hash():
                raise AutoRepairOperationConflict(
                    "REPAIR_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            return existing
        source = self.artifacts.load_source_exact(
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            artifact_version_id=spec.source_artifact_version_id,
        )
        if source.original_head_version_id != source.artifact_version_id:
            raise RepairStaleConflict("REPAIR_SOURCE_IS_NOT_BRANCH_HEAD")
        initial_quality = self.quality.get_result(
            organization_id=spec.organization_id,
            quality_result_id=spec.quality_result_id,
        )
        if initial_quality.artifact_version_id != source.artifact_version_id:
            raise ValueError("REPAIR_QUALITY_SOURCE_VERSION_MISMATCH")
        if initial_quality.status in _PASS_QUALITY:
            raise ValueError("REPAIR_SOURCE_ALREADY_PASSES_QUALITY")
        return self.repository.create(
            AutoRepairJob(
                job_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"lumi:auto-repair:{spec.organization_id}:{spec.operation_id}",
                    )
                ),
                spec=spec,
                status=RepairLoopStatus.PLANNED,
                original_source=source,
                working_source=source,
                current_quality=initial_quality,
            )
        )

    async def resume(self, job_id: str) -> AutoRepairJob:
        job = self.repository.get(job_id)
        if job.status in _TERMINAL:
            return job
        if job.next_iteration > job.spec.policy.max_iterations:
            return self._save_status(
                job,
                RepairLoopStatus.REVIEW_REQUIRED,
                "REPAIR_MAX_ITERATIONS_REACHED",
            )

        plan = self.planner.plan(spec=job.spec, job=job)
        if plan.kind is RepairKind.MANUAL_REVIEW:
            status = (
                RepairLoopStatus.BUDGET_EXHAUSTED
                if any("BUDGET" in reason for reason in plan.reason_codes)
                else RepairLoopStatus.REVIEW_REQUIRED
            )
            return self.repository.save(
                replace(
                    job,
                    status=status,
                    reason_codes=self._reasons(job, *plan.reason_codes),
                )
            )

        estimate_result = await self._estimate(job, plan)
        if isinstance(estimate_result, AutoRepairJob):
            return estimate_result
        plan, estimate = estimate_result
        if plan.paid and estimate.amount_usd > job.remaining_budget_usd:
            fallback_result = await self._fallback_to_free(job, plan)
            if isinstance(fallback_result, AutoRepairJob):
                return fallback_result
            plan, estimate = fallback_result

        preflight = await self.constraints.preflight(job=job, plan=plan)
        if preflight.unavailable:
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.REJECTED_PREFLIGHT,
                "REPAIR_PREFLIGHT_UNAVAILABLE",
                preflight=preflight,
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        if not preflight.passed or preflight.blocking_codes:
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.REJECTED_PREFLIGHT,
                "REPAIR_PREFLIGHT_BLOCKED",
                preflight=preflight,
            )

        repair_branch_id = self.artifacts.fork_repair_branch(
            source=job.working_source,
            repair_job_id=job.job_id,
            iteration=plan.iteration,
            actor_id=job.spec.requested_by,
        )
        reservation_result = await self._reserve(job, plan, estimate, preflight)
        if isinstance(reservation_result, AutoRepairJob):
            return reservation_result
        reservation = reservation_result

        execution_result = await self._execute_candidate(
            job=job,
            plan=plan,
            estimate=estimate,
            preflight=preflight,
            repair_branch_id=repair_branch_id,
            reservation=reservation,
        )
        if isinstance(execution_result, AutoRepairJob):
            return execution_result
        candidate = execution_result
        reservation_id = reservation.reservation_id if reservation else None
        spent = job.spent_usd + candidate.actual_cost_usd

        if plan.paid and (
            candidate.provider != estimate.provider or candidate.model != estimate.model
        ):
            return self._record_candidate(
                job,
                plan=plan,
                candidate=candidate,
                after=None,
                spent=spent,
                preflight=preflight,
                postflight=None,
                decision=RepairAttemptDecision.COST_RECONCILIATION_REQUIRED,
                reason="REPAIR_PAID_ROUTE_CHANGED_AFTER_RESERVATION",
                reservation_id=reservation_id,
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        if reservation is not None:
            try:
                await self.budget.commit(
                    job=job,
                    reservation=reservation,
                    candidate=candidate,
                    estimate=estimate,
                )
            except Exception as exc:
                return self._record_candidate(
                    job,
                    plan=plan,
                    candidate=candidate,
                    after=None,
                    spent=spent,
                    preflight=preflight,
                    postflight=None,
                    decision=RepairAttemptDecision.COST_RECONCILIATION_REQUIRED,
                    reason=(
                        "REPAIR_COST_SETTLEMENT_REQUIRES_RECONCILIATION:"
                        f"{type(exc).__name__}"
                    ),
                    reservation_id=reservation_id,
                    terminal=RepairLoopStatus.REVIEW_REQUIRED,
                )
        if spent > job.spec.policy.max_total_cost_usd:
            return self._record_candidate(
                job,
                plan=plan,
                candidate=candidate,
                after=None,
                spent=spent,
                preflight=preflight,
                postflight=None,
                decision=RepairAttemptDecision.BUDGET_EXHAUSTED,
                reason="REPAIR_ACTUAL_COST_EXCEEDED_LOOP_BUDGET",
                reservation_id=reservation_id,
                terminal=RepairLoopStatus.BUDGET_EXHAUSTED,
            )

        postflight = await self.constraints.postflight(
            job=job,
            plan=plan,
            candidate=candidate,
        )
        if postflight.unavailable:
            return self._record_candidate(
                job,
                plan=plan,
                candidate=candidate,
                after=None,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_POSTFLIGHT,
                reason="REPAIR_POSTFLIGHT_UNAVAILABLE",
                reservation_id=reservation_id,
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        if not postflight.passed or postflight.blocking_codes:
            return self._record_candidate(
                job,
                plan=plan,
                candidate=candidate,
                after=None,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_POSTFLIGHT,
                reason="REPAIR_POSTFLIGHT_BLOCKED",
                reservation_id=reservation_id,
            )

        quality_result = await self._evaluate_candidate(
            job=job,
            plan=plan,
            candidate=candidate,
            spent=spent,
            preflight=preflight,
            postflight=postflight,
            reservation_id=reservation_id,
        )
        if isinstance(quality_result, AutoRepairJob):
            return quality_result
        after = quality_result
        rejection = self._candidate_rejection(job, after)
        if rejection is not None:
            decision, reason = rejection
            return self._record_candidate(
                job,
                plan=plan,
                candidate=candidate,
                after=after,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=decision,
                reason=reason,
                reservation_id=reservation_id,
            )

        delta = after.overall_score - job.current_quality.overall_score
        if after.status in _PASS_QUALITY:
            return await self._promote_exact(
                job=job,
                plan=plan,
                candidate=candidate,
                candidate_quality=after,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                delta=delta,
                reservation_id=reservation_id,
            )
        if after.status not in _REPAIRABLE_QUALITY:
            return self._record_candidate(
                job,
                plan=plan,
                candidate=candidate,
                after=after,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_INSUFFICIENT_GAIN,
                reason="REPAIR_CANDIDATE_REQUIRES_MANUAL_REVIEW",
                reservation_id=reservation_id,
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        return self._accept_intermediate(
            job=job,
            plan=plan,
            candidate=candidate,
            after=after,
            spent=spent,
            preflight=preflight,
            postflight=postflight,
            delta=delta,
            reservation_id=reservation_id,
        )

    async def _estimate(
        self,
        job: AutoRepairJob,
        plan: RepairPlan,
    ) -> tuple[RepairPlan, RepairCostEstimate] | AutoRepairJob:
        try:
            estimate = await self.executor.estimate(job=job, plan=plan)
        except Exception as exc:
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.EXECUTION_FAILED,
                f"REPAIR_ESTIMATE_FAILED:{type(exc).__name__}",
            )
        return DeterministicRepairPlanner.with_estimate(plan, estimate.amount_usd), estimate

    async def _fallback_to_free(
        self,
        job: AutoRepairJob,
        paid_plan: RepairPlan,
    ) -> tuple[RepairPlan, RepairCostEstimate] | AutoRepairJob:
        free_spec = replace(
            job.spec,
            policy=replace(job.spec.policy, allow_paid_repairs=False),
        )
        fallback = self.planner.plan(spec=free_spec, job=job)
        if fallback.kind is RepairKind.MANUAL_REVIEW or fallback.paid:
            return self._record_no_candidate(
                job,
                paid_plan,
                RepairAttemptDecision.BUDGET_EXHAUSTED,
                "REPAIR_BUDGET_EXHAUSTED",
                terminal=RepairLoopStatus.BUDGET_EXHAUSTED,
            )
        estimate_result = await self._estimate(job, fallback)
        if isinstance(estimate_result, AutoRepairJob):
            return estimate_result
        plan, estimate = estimate_result
        if estimate.amount_usd != Decimal("0"):
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.BUDGET_EXHAUSTED,
                "REPAIR_FREE_FALLBACK_REPORTED_COST",
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        return plan, estimate

    async def _reserve(
        self,
        job: AutoRepairJob,
        plan: RepairPlan,
        estimate: RepairCostEstimate,
        preflight: ConstraintCheck,
    ) -> BudgetReservation | None | AutoRepairJob:
        if not plan.paid:
            return None
        try:
            return await self.budget.reserve(job=job, plan=plan, estimate=estimate)
        except Exception as exc:
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.BUDGET_EXHAUSTED,
                f"REPAIR_BUDGET_RESERVATION_FAILED:{type(exc).__name__}",
                preflight=preflight,
                terminal=RepairLoopStatus.BUDGET_EXHAUSTED,
            )

    async def _execute_candidate(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        estimate: RepairCostEstimate,
        preflight: ConstraintCheck,
        repair_branch_id: str,
        reservation: BudgetReservation | None,
    ) -> RepairCandidate | AutoRepairJob:
        try:
            return await self.executor.execute(
                job=job,
                plan=plan,
                repair_branch_id=repair_branch_id,
                reservation=reservation,
            )
        except RepairSideEffectUncertain as exc:
            detail = (
                f":{exc.external_operation_id}"
                if exc.external_operation_id is not None
                else ""
            )
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.COST_RECONCILIATION_REQUIRED,
                f"REPAIR_PAID_SIDE_EFFECT_REQUIRES_RECONCILIATION{detail}",
                preflight=preflight,
                reservation_id=reservation.reservation_id if reservation else None,
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        except Exception as exc:
            if reservation is not None:
                await self.budget.release(
                    job=job,
                    reservation=reservation,
                    estimate=estimate,
                    reason="repair-execution-failed-before-side-effect",
                )
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.EXECUTION_FAILED,
                f"REPAIR_EXECUTION_FAILED:{type(exc).__name__}",
                preflight=preflight,
                reservation_id=reservation.reservation_id if reservation else None,
            )

    async def _evaluate_candidate(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
        spent: Decimal,
        preflight: ConstraintCheck,
        postflight: ConstraintCheck,
        reservation_id: str | None,
    ) -> RepairQualitySnapshot | AutoRepairJob:
        try:
            after = await self.quality.evaluate_candidate(job=job, candidate=candidate)
        except Exception as exc:
            return self._record_candidate(
                job,
                plan=plan,
                candidate=candidate,
                after=None,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_POSTFLIGHT,
                reason=f"REPAIR_QUALITY_EVALUATION_FAILED:{type(exc).__name__}",
                reservation_id=reservation_id,
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        if after.artifact_version_id != candidate.artifact_version_id:
            return self._record_candidate(
                job,
                plan=plan,
                candidate=candidate,
                after=after,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_POSTFLIGHT,
                reason="REPAIR_QUALITY_CANDIDATE_VERSION_MISMATCH",
                reservation_id=reservation_id,
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        return after

    def _candidate_rejection(
        self,
        job: AutoRepairJob,
        after: RepairQualitySnapshot,
    ) -> tuple[RepairAttemptDecision, str] | None:
        new_hard = set(after.hard_violation_codes) - set(
            job.current_quality.hard_violation_codes
        )
        if new_hard:
            return (
                RepairAttemptDecision.REJECTED_NEW_HARD_VIOLATION,
                "REPAIR_INTRODUCED_NEW_HARD_VIOLATION",
            )
        delta = after.overall_score - job.current_quality.overall_score
        if delta < -job.spec.policy.max_score_regression:
            return (
                RepairAttemptDecision.REJECTED_REGRESSION,
                "REPAIR_SCORE_REGRESSION_EXCEEDED",
            )
        if delta < job.spec.policy.minimum_expected_gain:
            return (
                RepairAttemptDecision.REJECTED_INSUFFICIENT_GAIN,
                "REPAIR_MINIMUM_GAIN_NOT_MET",
            )
        return None

    def _accept_intermediate(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
        after: RepairQualitySnapshot,
        spent: Decimal,
        preflight: ConstraintCheck,
        postflight: ConstraintCheck,
        delta: float,
        reservation_id: str | None,
    ) -> AutoRepairJob:
        attempt = self._attempt(
            job=job,
            plan=plan,
            candidate=candidate,
            after=after,
            preflight=preflight,
            postflight=postflight,
            decision=RepairAttemptDecision.ACCEPTED_INTERMEDIATE,
            delta=delta,
            reservation_id=reservation_id,
        )
        if plan.iteration >= job.spec.policy.max_iterations:
            return self._save_attempt(
                job,
                attempt,
                RepairLoopStatus.REVIEW_REQUIRED,
                spent,
                "REPAIR_MAX_ITERATIONS_REACHED_AFTER_IMPROVEMENT",
            )
        working_source = self.artifacts.load_source_exact(
            organization_id=job.spec.organization_id,
            project_id=job.spec.project_id,
            artifact_version_id=candidate.artifact_version_id,
        )
        return self.repository.save(
            replace(
                job,
                status=RepairLoopStatus.RUNNING,
                working_source=working_source,
                current_quality=after,
                attempts=(*job.attempts, attempt),
                spent_usd=spent,
                reason_codes=self._reasons(
                    job, "REPAIR_INTERMEDIATE_IMPROVEMENT_ACCEPTED"
                ),
            )
        )

    async def _promote_exact(
        self,
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
        candidate_quality: RepairQualitySnapshot,
        spent: Decimal,
        preflight: ConstraintCheck,
        postflight: ConstraintCheck,
        delta: float,
        reservation_id: str | None,
    ) -> AutoRepairJob:
        try:
            promoted = self.artifacts.promote_candidate(
                original_source=job.original_source,
                candidate=candidate,
                repair_job_id=job.job_id,
                actor_id=job.spec.requested_by,
            )
        except RepairStaleConflict:
            return self._promotion_stale(
                job,
                plan,
                candidate,
                candidate_quality,
                spent,
                preflight,
                postflight,
                delta,
                reservation_id,
                promoted=None,
                promotion_quality=None,
            )
        if promoted.artifact_content_hash != candidate.artifact_content_hash:
            return self._promotion_failure(
                job,
                plan,
                candidate,
                candidate_quality,
                promoted,
                None,
                spent,
                preflight,
                postflight,
                delta,
                reservation_id,
                "REPAIR_PROMOTION_CONTENT_HASH_DRIFT",
            )
        try:
            promotion_quality = await self.quality.evaluate_candidate(
                job=job, candidate=promoted
            )
        except Exception as exc:
            return self._promotion_failure(
                job,
                plan,
                candidate,
                candidate_quality,
                promoted,
                None,
                spent,
                preflight,
                postflight,
                delta,
                reservation_id,
                f"REPAIR_PROMOTION_EXACT_QUALITY_FAILED:{type(exc).__name__}",
            )
        promotion_reason = self._promotion_quality_failure_reason(
            job=job,
            candidate_quality=candidate_quality,
            promoted=promoted,
            promotion_quality=promotion_quality,
        )
        if promotion_reason is not None:
            return self._promotion_failure(
                job,
                plan,
                candidate,
                candidate_quality,
                promoted,
                promotion_quality,
                spent,
                preflight,
                postflight,
                delta,
                reservation_id,
                promotion_reason,
            )
        try:
            final_version_id = self.artifacts.approve_promoted_version(
                promoted=promoted,
                quality=promotion_quality,
                repair_job_id=job.job_id,
            )
        except RepairStaleConflict:
            return self._promotion_stale(
                job,
                plan,
                candidate,
                candidate_quality,
                spent,
                preflight,
                postflight,
                delta,
                reservation_id,
                promoted=promoted,
                promotion_quality=promotion_quality,
            )
        except Exception as exc:
            return self._promotion_failure(
                job,
                plan,
                candidate,
                candidate_quality,
                promoted,
                promotion_quality,
                spent,
                preflight,
                postflight,
                delta,
                reservation_id,
                f"REPAIR_PROMOTION_APPROVAL_FAILED:{type(exc).__name__}",
                decision=RepairAttemptDecision.PROMOTION_APPROVAL_FAILED,
            )
        if final_version_id != promoted.artifact_version_id:
            return self._promotion_failure(
                job,
                plan,
                candidate,
                candidate_quality,
                promoted,
                promotion_quality,
                spent,
                preflight,
                postflight,
                delta,
                reservation_id,
                "REPAIR_APPROVAL_RETURNED_DIFFERENT_VERSION",
                decision=RepairAttemptDecision.PROMOTION_APPROVAL_FAILED,
            )
        attempt = self._attempt(
            job=job,
            plan=plan,
            candidate=candidate,
            after=candidate_quality,
            preflight=preflight,
            postflight=postflight,
            decision=RepairAttemptDecision.PROMOTED,
            delta=delta,
            reservation_id=reservation_id,
            promoted=promoted,
            promotion_quality=promotion_quality,
        )
        return self.repository.save(
            replace(
                job,
                status=RepairLoopStatus.READY,
                attempts=(*job.attempts, attempt),
                spent_usd=spent,
                final_artifact_version_id=final_version_id,
                reason_codes=self._reasons(
                    job, "REPAIR_PROMOTED_AFTER_EXACT_MAIN_QUALITY_PASS"
                ),
            )
        )

    @staticmethod
    def _promotion_quality_failure_reason(
        *,
        job: AutoRepairJob,
        candidate_quality: RepairQualitySnapshot,
        promoted: RepairCandidate,
        promotion_quality: RepairQualitySnapshot,
    ) -> str | None:
        if promotion_quality.artifact_version_id != promoted.artifact_version_id:
            return "REPAIR_PROMOTION_QUALITY_VERSION_MISMATCH"
        if promotion_quality.status not in _PASS_QUALITY:
            return "REPAIR_PROMOTION_EXACT_QUALITY_NOT_PASSING"
        if (
            promotion_quality.profile_id != candidate_quality.profile_id
            or promotion_quality.profile_version != candidate_quality.profile_version
            or promotion_quality.profile_hash != candidate_quality.profile_hash
        ):
            return "REPAIR_PROMOTION_QUALITY_PROFILE_CHANGED"
        if set(promotion_quality.hard_violation_codes) - set(
            candidate_quality.hard_violation_codes
        ):
            return "REPAIR_PROMOTION_INTRODUCED_HARD_VIOLATION"
        score_drift = promotion_quality.overall_score - candidate_quality.overall_score
        if score_drift < -job.spec.policy.max_score_regression:
            return "REPAIR_PROMOTION_QUALITY_DRIFT_EXCEEDED"
        return None

    def _promotion_stale(
        self,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
        candidate_quality: RepairQualitySnapshot,
        spent: Decimal,
        preflight: ConstraintCheck,
        postflight: ConstraintCheck,
        delta: float,
        reservation_id: str | None,
        *,
        promoted: RepairCandidate | None,
        promotion_quality: RepairQualitySnapshot | None,
    ) -> AutoRepairJob:
        attempt = self._attempt(
            job=job,
            plan=plan,
            candidate=candidate,
            after=candidate_quality,
            preflight=preflight,
            postflight=postflight,
            decision=RepairAttemptDecision.PROMOTION_STALE_CONFLICT,
            delta=delta,
            reservation_id=reservation_id,
            promoted=promoted,
            promotion_quality=promotion_quality,
            reasons=("REPAIR_MAIN_BRANCH_HEAD_CHANGED",),
        )
        return self._save_attempt(
            job,
            attempt,
            RepairLoopStatus.STALE_CONFLICT,
            spent,
            "REPAIR_MAIN_BRANCH_HEAD_CHANGED",
        )

    def _promotion_failure(
        self,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
        candidate_quality: RepairQualitySnapshot,
        promoted: RepairCandidate | None,
        promotion_quality: RepairQualitySnapshot | None,
        spent: Decimal,
        preflight: ConstraintCheck,
        postflight: ConstraintCheck,
        delta: float,
        reservation_id: str | None,
        reason: str,
        *,
        decision: RepairAttemptDecision = RepairAttemptDecision.PROMOTION_VALIDATION_FAILED,
    ) -> AutoRepairJob:
        attempt = self._attempt(
            job=job,
            plan=plan,
            candidate=candidate,
            after=candidate_quality,
            preflight=preflight,
            postflight=postflight,
            decision=decision,
            delta=delta,
            reservation_id=reservation_id,
            promoted=promoted,
            promotion_quality=promotion_quality,
            reasons=(reason,),
        )
        return self._save_attempt(
            job,
            attempt,
            RepairLoopStatus.REVIEW_REQUIRED,
            spent,
            reason,
        )

    def cancel(self, job_id: str) -> AutoRepairJob:
        job = self.repository.get(job_id)
        if job.status in _TERMINAL:
            return job
        return self._save_status(job, RepairLoopStatus.CANCELLED, "REPAIR_CANCELLED")

    def _record_no_candidate(
        self,
        job: AutoRepairJob,
        plan: RepairPlan,
        decision: RepairAttemptDecision,
        reason: str,
        *,
        preflight: ConstraintCheck | None = None,
        reservation_id: str | None = None,
        terminal: RepairLoopStatus | None = None,
    ) -> AutoRepairJob:
        attempt = self._attempt(
            job=job,
            plan=plan,
            candidate=None,
            after=None,
            preflight=preflight,
            postflight=None,
            decision=decision,
            delta=None,
            reservation_id=reservation_id,
            reasons=(reason,),
        )
        return self._save_attempt(
            job,
            attempt,
            terminal or self._next_status(job, plan.iteration),
            job.spent_usd,
            reason,
        )

    def _record_candidate(
        self,
        job: AutoRepairJob,
        *,
        plan: RepairPlan,
        candidate: RepairCandidate,
        after: RepairQualitySnapshot | None,
        spent: Decimal,
        preflight: ConstraintCheck | None,
        postflight: ConstraintCheck | None,
        decision: RepairAttemptDecision,
        reason: str,
        reservation_id: str | None,
        terminal: RepairLoopStatus | None = None,
    ) -> AutoRepairJob:
        delta = (
            None
            if after is None
            else after.overall_score - job.current_quality.overall_score
        )
        attempt = self._attempt(
            job=job,
            plan=plan,
            candidate=candidate,
            after=after,
            preflight=preflight,
            postflight=postflight,
            decision=decision,
            delta=delta,
            reservation_id=reservation_id,
            reasons=(reason,),
        )
        return self._save_attempt(
            job,
            attempt,
            terminal or self._next_status(job, plan.iteration),
            spent,
            reason,
        )

    @staticmethod
    def _attempt(
        *,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate | None,
        after: RepairQualitySnapshot | None,
        preflight: ConstraintCheck | None,
        postflight: ConstraintCheck | None,
        decision: RepairAttemptDecision,
        delta: float | None,
        reservation_id: str | None,
        promoted: RepairCandidate | None = None,
        promotion_quality: RepairQualitySnapshot | None = None,
        reasons: tuple[str, ...] = (),
    ) -> RepairAttempt:
        return RepairAttempt(
            iteration=plan.iteration,
            source_artifact_version_id=job.working_source.artifact_version_id,
            before_quality_result_id=job.current_quality.quality_result_id,
            before_score=job.current_quality.overall_score,
            plan=plan,
            candidate=candidate,
            after_quality_result_id=after.quality_result_id if after else None,
            after_score=after.overall_score if after else None,
            score_delta=delta,
            decision=decision,
            preflight=preflight,
            postflight=postflight,
            reservation_id=reservation_id,
            actual_cost_usd=candidate.actual_cost_usd if candidate else Decimal("0"),
            promoted_artifact_version_id=(promoted.artifact_version_id if promoted else None),
            promotion_quality_result_id=(
                promotion_quality.quality_result_id if promotion_quality else None
            ),
            reason_codes=reasons,
        )

    def _save_attempt(
        self,
        job: AutoRepairJob,
        attempt: RepairAttempt,
        status: RepairLoopStatus,
        spent: Decimal,
        reason: str,
    ) -> AutoRepairJob:
        return self.repository.save(
            replace(
                job,
                status=status,
                attempts=(*job.attempts, attempt),
                spent_usd=spent,
                reason_codes=self._reasons(job, reason),
            )
        )

    def _save_status(
        self,
        job: AutoRepairJob,
        status: RepairLoopStatus,
        reason: str,
    ) -> AutoRepairJob:
        return self.repository.save(
            replace(job, status=status, reason_codes=self._reasons(job, reason))
        )

    def _next_status(self, job: AutoRepairJob, iteration: int) -> RepairLoopStatus:
        if iteration >= job.spec.policy.max_iterations:
            return RepairLoopStatus.REVIEW_REQUIRED
        return RepairLoopStatus.RUNNING

    @staticmethod
    def _reasons(job: AutoRepairJob, *values: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*job.reason_codes, *values)))
