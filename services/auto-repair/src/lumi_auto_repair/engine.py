from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

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
    """Raised only when a paid side effect may have started and must reconcile."""


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
    """Execute at most one repair candidate per resume call."""

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
        quality = self.quality.get_result(
            organization_id=spec.organization_id,
            quality_result_id=spec.quality_result_id,
        )
        if quality.artifact_version_id != source.artifact_version_id:
            raise ValueError("REPAIR_QUALITY_SOURCE_VERSION_MISMATCH")
        if quality.status in _PASS_QUALITY:
            raise ValueError("REPAIR_SOURCE_ALREADY_PASSES_QUALITY")
        job = AutoRepairJob(
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
            current_quality=quality,
        )
        return self.repository.create(job)

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
                if any("BUDGET" in code for code in plan.reason_codes)
                else RepairLoopStatus.REVIEW_REQUIRED
            )
            return self.repository.save(
                replace(
                    job,
                    status=status,
                    reason_codes=self._reasons(job, *plan.reason_codes),
                )
            )

        try:
            estimate = await self.executor.estimate(job=job, plan=plan)
        except Exception as exc:
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.EXECUTION_FAILED,
                f"REPAIR_ESTIMATE_FAILED:{type(exc).__name__}",
            )
        plan = DeterministicRepairPlanner.with_estimate(
            plan,
            estimate.amount_usd,
        )
        if plan.paid and estimate.amount_usd > job.remaining_budget_usd:
            fallback = self._free_fallback(job)
            if fallback is None:
                return self._record_no_candidate(
                    job,
                    plan,
                    RepairAttemptDecision.BUDGET_EXHAUSTED,
                    "REPAIR_BUDGET_EXHAUSTED",
                    terminal=RepairLoopStatus.BUDGET_EXHAUSTED,
                )
            plan = fallback
            try:
                estimate = await self.executor.estimate(job=job, plan=plan)
            except Exception as exc:
                return self._record_no_candidate(
                    job,
                    plan,
                    RepairAttemptDecision.EXECUTION_FAILED,
                    f"REPAIR_FREE_ESTIMATE_FAILED:{type(exc).__name__}",
                )
            plan = DeterministicRepairPlanner.with_estimate(
                plan,
                estimate.amount_usd,
            )
            if estimate.amount_usd != Decimal("0"):
                return self._record_no_candidate(
                    job,
                    plan,
                    RepairAttemptDecision.BUDGET_EXHAUSTED,
                    "REPAIR_FREE_FALLBACK_REPORTED_COST",
                    terminal=RepairLoopStatus.REVIEW_REQUIRED,
                )

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
        reservation: BudgetReservation | None = None
        if plan.paid:
            try:
                reservation = await self.budget.reserve(
                    job=job,
                    plan=plan,
                    estimate=estimate,
                )
            except Exception as exc:
                return self._record_no_candidate(
                    job,
                    plan,
                    RepairAttemptDecision.BUDGET_EXHAUSTED,
                    f"REPAIR_BUDGET_RESERVATION_FAILED:{type(exc).__name__}",
                    preflight=preflight,
                    terminal=RepairLoopStatus.BUDGET_EXHAUSTED,
                )

        try:
            candidate = await self.executor.execute(
                job=job,
                plan=plan,
                repair_branch_id=repair_branch_id,
                reservation=reservation,
            )
        except RepairSideEffectUncertain:
            return self._record_no_candidate(
                job,
                plan,
                RepairAttemptDecision.EXECUTION_FAILED,
                "REPAIR_PAID_SIDE_EFFECT_REQUIRES_RECONCILIATION",
                preflight=preflight,
                reservation_id=(
                    reservation.reservation_id if reservation else None
                ),
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
                reservation_id=(
                    reservation.reservation_id if reservation else None
                ),
            )

        if plan.paid and (
            candidate.provider != estimate.provider
            or candidate.model != estimate.model
        ):
            return self._record_candidate_without_quality(
                job,
                plan=plan,
                candidate=candidate,
                preflight=preflight,
                decision=RepairAttemptDecision.EXECUTION_FAILED,
                reason="REPAIR_PAID_ROUTE_CHANGED_AFTER_RESERVATION",
                reservation_id=(
                    reservation.reservation_id if reservation else None
                ),
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        if reservation is not None:
            await self.budget.commit(
                job=job,
                reservation=reservation,
                candidate=candidate,
                estimate=estimate,
            )
        spent = job.spent_usd + candidate.actual_cost_usd

        postflight = await self.constraints.postflight(
            job=job,
            plan=plan,
            candidate=candidate,
        )
        if postflight.unavailable:
            return self._reject_candidate(
                job,
                plan=plan,
                candidate=candidate,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_POSTFLIGHT,
                reason="REPAIR_POSTFLIGHT_UNAVAILABLE",
                reservation_id=(
                    reservation.reservation_id if reservation else None
                ),
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        if not postflight.passed or postflight.blocking_codes:
            return self._reject_candidate(
                job,
                plan=plan,
                candidate=candidate,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_POSTFLIGHT,
                reason="REPAIR_POSTFLIGHT_BLOCKED",
                reservation_id=(
                    reservation.reservation_id if reservation else None
                ),
            )

        try:
            after = await self.quality.evaluate_candidate(
                job=job,
                candidate=candidate,
            )
        except Exception as exc:
            return self._reject_candidate(
                job,
                plan=plan,
                candidate=candidate,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_POSTFLIGHT,
                reason=(
                    f"REPAIR_QUALITY_EVALUATION_FAILED:{type(exc).__name__}"
                ),
                reservation_id=(
                    reservation.reservation_id if reservation else None
                ),
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )
        if after.artifact_version_id != candidate.artifact_version_id:
            return self._reject_candidate(
                job,
                plan=plan,
                candidate=candidate,
                spent=spent,
                preflight=preflight,
                postflight=postflight,
                decision=RepairAttemptDecision.REJECTED_POSTFLIGHT,
                reason="REPAIR_QUALITY_CANDIDATE_VERSION_MISMATCH",
                reservation_id=(
                    reservation.reservation_id if reservation else None
                ),
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )

        delta = after.overall_score - job.current_quality.overall_score
        new_hard = sorted(
            set(after.hard_violation_codes)
            - set(job.current_quality.hard_violation_codes)
        )
        reservation_id = (
            reservation.reservation_id if reservation else None
        )
        if new_hard:
            return self._reject_scored(
                job,
                plan,
                candidate,
                after,
                spent,
                preflight,
                postflight,
                delta,
                RepairAttemptDecision.REJECTED_NEW_HARD_VIOLATION,
                "REPAIR_INTRODUCED_NEW_HARD_VIOLATION",
                reservation_id,
            )
        if delta < -job.spec.policy.max_score_regression:
            return self._reject_scored(
                job,
                plan,
                candidate,
                after,
                spent,
                preflight,
                postflight,
                delta,
                RepairAttemptDecision.REJECTED_REGRESSION,
                "REPAIR_SCORE_REGRESSION_EXCEEDED",
                reservation_id,
            )
        if delta < job.spec.policy.minimum_expected_gain:
            return self._reject_scored(
                job,
                plan,
                candidate,
                after,
                spent,
                preflight,
                postflight,
                delta,
                RepairAttemptDecision.REJECTED_INSUFFICIENT_GAIN,
                "REPAIR_MINIMUM_GAIN_NOT_MET",
                reservation_id,
            )

        if after.status in _PASS_QUALITY:
            attempt = self._attempt(
                job,
                plan,
                candidate,
                after,
                preflight,
                postflight,
                RepairAttemptDecision.PROMOTED,
                delta,
                reservation_id,
                (),
            )
            provisional = replace(
                job,
                status=RepairLoopStatus.RUNNING,
                attempts=(*job.attempts, attempt),
                spent_usd=spent,
            )
            try:
                final_version_id = self.artifacts.promote_candidate(
                    original_source=job.original_source,
                    candidate=candidate,
                    quality=after,
                    repair_job_id=job.job_id,
                    actor_id=job.spec.requested_by,
                )
            except RepairStaleConflict:
                return self._save_status(
                    provisional,
                    RepairLoopStatus.STALE_CONFLICT,
                    "REPAIR_MAIN_BRANCH_HEAD_CHANGED",
                )
            return self.repository.save(
                replace(
                    provisional,
                    status=RepairLoopStatus.READY,
                    final_artifact_version_id=final_version_id,
                    reason_codes=self._reasons(
                        provisional,
                        "REPAIR_PROMOTED_AFTER_QUALITY_PASS",
                    ),
                )
            )

        if after.status not in _REPAIRABLE_QUALITY:
            return self._reject_scored(
                job,
                plan,
                candidate,
                after,
                spent,
                preflight,
                postflight,
                delta,
                RepairAttemptDecision.REJECTED_INSUFFICIENT_GAIN,
                "REPAIR_CANDIDATE_REQUIRES_MANUAL_REVIEW",
                reservation_id,
                terminal=RepairLoopStatus.REVIEW_REQUIRED,
            )

        attempt = self._attempt(
            job,
            plan,
            candidate,
            after,
            preflight,
            postflight,
            RepairAttemptDecision.ACCEPTED_INTERMEDIATE,
            delta,
            reservation_id,
            (),
        )
        if plan.iteration >= job.spec.policy.max_iterations:
            return self.repository.save(
                replace(
                    job,
                    status=RepairLoopStatus.REVIEW_REQUIRED,
                    attempts=(*job.attempts, attempt),
                    spent_usd=spent,
                    reason_codes=self._reasons(
                        job,
                        "REPAIR_MAX_ITERATIONS_REACHED_AFTER_IMPROVEMENT",
                    ),
                )
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
                    job,
                    "REPAIR_INTERMEDIATE_IMPROVEMENT_ACCEPTED",
                ),
            )
        )

    def cancel(self, job_id: str) -> AutoRepairJob:
        job = self.repository.get(job_id)
        if job.status in _TERMINAL:
            return job
        return self._save_status(
            job,
            RepairLoopStatus.CANCELLED,
            "REPAIR_CANCELLED",
        )

    def _free_fallback(self, job: AutoRepairJob) -> RepairPlan | None:
        free_spec = replace(
            job.spec,
            policy=replace(job.spec.policy, allow_paid_repairs=False),
        )
        fallback = self.planner.plan(spec=free_spec, job=job)
        if fallback.kind is RepairKind.MANUAL_REVIEW or fallback.paid:
            return None
        return fallback

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
        attempt = RepairAttempt(
            iteration=plan.iteration,
            source_artifact_version_id=job.working_source.artifact_version_id,
            before_quality_result_id=job.current_quality.quality_result_id,
            before_score=job.current_quality.overall_score,
            plan=plan,
            candidate=None,
            after_quality_result_id=None,
            after_score=None,
            score_delta=None,
            decision=decision,
            preflight=preflight,
            reservation_id=reservation_id,
            reason_codes=(reason,),
        )
        return self._save_attempt(
            job,
            attempt,
            terminal or self._next_status(job, plan.iteration),
            job.spent_usd,
            reason,
        )

    def _record_candidate_without_quality(
        self,
        job: AutoRepairJob,
        *,
        plan: RepairPlan,
        candidate: RepairCandidate,
        preflight: ConstraintCheck,
        decision: RepairAttemptDecision,
        reason: str,
        reservation_id: str | None,
        terminal: RepairLoopStatus,
    ) -> AutoRepairJob:
        attempt = self._attempt(
            job,
            plan,
            candidate,
            None,
            preflight,
            None,
            decision,
            None,
            reservation_id,
            (reason,),
        )
        return self._save_attempt(
            job,
            attempt,
            terminal,
            job.spent_usd + candidate.actual_cost_usd,
            reason,
        )

    def _reject_candidate(
        self,
        job: AutoRepairJob,
        *,
        plan: RepairPlan,
        candidate: RepairCandidate,
        spent: Decimal,
        preflight: ConstraintCheck,
        postflight: ConstraintCheck,
        decision: RepairAttemptDecision,
        reason: str,
        reservation_id: str | None,
        terminal: RepairLoopStatus | None = None,
    ) -> AutoRepairJob:
        attempt = self._attempt(
            job,
            plan,
            candidate,
            None,
            preflight,
            postflight,
            decision,
            None,
            reservation_id,
            (reason,),
        )
        return self._save_attempt(
            job,
            attempt,
            terminal or self._next_status(job, plan.iteration),
            spent,
            reason,
        )

    def _reject_scored(
        self,
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
        after: RepairQualitySnapshot,
        spent: Decimal,
        preflight: ConstraintCheck,
        postflight: ConstraintCheck,
        delta: float,
        decision: RepairAttemptDecision,
        reason: str,
        reservation_id: str | None,
        *,
        terminal: RepairLoopStatus | None = None,
    ) -> AutoRepairJob:
        attempt = self._attempt(
            job,
            plan,
            candidate,
            after,
            preflight,
            postflight,
            decision,
            delta,
            reservation_id,
            (reason,),
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
        job: AutoRepairJob,
        plan: RepairPlan,
        candidate: RepairCandidate,
        after: RepairQualitySnapshot | None,
        preflight: ConstraintCheck | None,
        postflight: ConstraintCheck | None,
        decision: RepairAttemptDecision,
        delta: float | None,
        reservation_id: str | None,
        reasons: tuple[str, ...],
    ) -> RepairAttempt:
        return RepairAttempt(
            iteration=plan.iteration,
            source_artifact_version_id=job.working_source.artifact_version_id,
            before_quality_result_id=job.current_quality.quality_result_id,
            before_score=job.current_quality.overall_score,
            plan=plan,
            candidate=candidate,
            after_quality_result_id=(
                after.quality_result_id if after is not None else None
            ),
            after_score=(after.overall_score if after is not None else None),
            score_delta=delta,
            decision=decision,
            preflight=preflight,
            postflight=postflight,
            reservation_id=reservation_id,
            actual_cost_usd=candidate.actual_cost_usd,
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
            replace(
                job,
                status=status,
                reason_codes=self._reasons(job, reason),
            )
        )

    def _next_status(
        self,
        job: AutoRepairJob,
        iteration: int,
    ) -> RepairLoopStatus:
        if iteration >= job.spec.policy.max_iterations:
            return RepairLoopStatus.REVIEW_REQUIRED
        return RepairLoopStatus.RUNNING

    @staticmethod
    def _reasons(job: AutoRepairJob, *values: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*job.reason_codes, *values)))
