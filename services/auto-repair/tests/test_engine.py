from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from lumi_auto_repair import (
    AutoRepairEngine,
    AutoRepairTaskSpec,
    BudgetReservation,
    ConstraintCheck,
    InMemoryAutoRepairRepository,
    RepairAttemptDecision,
    RepairCandidate,
    RepairCostEstimate,
    RepairDirective,
    RepairKind,
    RepairLoopStatus,
    RepairPolicySnapshot,
    RepairQualitySnapshot,
    RepairSideEffectUncertain,
    RepairSourceSnapshot,
    RepairStaleConflict,
)


def _id() -> str:
    return str(uuid4())


def _directive(
    *,
    action: str = "REPLACE_TEXT",
    code: str = "TEXT_OVERFLOW",
    target: str | None = None,
    protected: tuple[str, ...] = (),
) -> RepairDirective:
    return RepairDirective(
        directive_id=_id(),
        source_violation_id=_id(),
        violation_code=code,
        dimension="TYPOGRAPHY" if action == "REPLACE_TEXT" else "DEFECTS",
        severity="ERROR",
        blocking=False,
        action_type=action,
        target=target or _id(),
        parameters=(
            {"text": "Short title"}
            if action == "REPLACE_TEXT"
            else {"instruction": "remove background noise only"}
        ),
        protected_refs=protected,
    )


def _quality(
    version_id: str,
    *,
    result_id: str | None = None,
    status: str = "FAIL_REPAIRABLE",
    score: float = 55.0,
    hard: tuple[str, ...] = (),
    directives: tuple[RepairDirective, ...] = (),
    profile_hash: str = "b" * 64,
) -> RepairQualitySnapshot:
    return RepairQualitySnapshot(
        quality_result_id=result_id or _id(),
        artifact_version_id=version_id,
        status=status,
        overall_score=score,
        overall_confidence=0.92,
        hard_violation_codes=hard,
        directives=directives,
        profile_id="general-v1",
        profile_version=1,
        profile_hash=profile_hash,
    )


def _source(version_id: str, *, artifact_type: str = "DESIGN_DOCUMENT") -> RepairSourceSnapshot:
    branch_id = _id()
    return RepairSourceSnapshot(
        organization_id=ORG,
        project_id=PROJECT,
        artifact_id=_id(),
        artifact_version_id=version_id,
        artifact_content_hash="a" * 64,
        artifact_type=artifact_type,
        original_branch_id=branch_id,
        original_head_version_id=version_id,
        design_document_id=_id() if artifact_type == "DESIGN_DOCUMENT" else None,
        design_document_version_id=_id() if artifact_type == "DESIGN_DOCUMENT" else None,
        constraint_snapshot_hash="c" * 64,
        protected_refs=("logo:primary",),
    )


def _policy(
    *,
    budget: str = "5.00",
    max_iterations: int = 2,
    kinds: frozenset[RepairKind] | None = None,
) -> RepairPolicySnapshot:
    return RepairPolicySnapshot(
        policy_id="default-auto-repair",
        version=1,
        max_iterations=max_iterations,
        max_total_cost_usd=Decimal(budget),
        minimum_expected_gain=2.0,
        max_score_regression=1.0,
        allowed_kinds=kinds
        or frozenset(
            {
                RepairKind.COPY_TYPOGRAPHY_FIX,
                RepairKind.STRUCTURAL_DESIGN_OP,
                RepairKind.LOCAL_IMAGE_EDIT,
            }
        ),
    )


def _spec(source: RepairSourceSnapshot, initial: RepairQualitySnapshot, policy=None):
    return AutoRepairTaskSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=_id(),
        requested_by="repair-agent",
        source_artifact_version_id=source.artifact_version_id,
        quality_result_id=initial.quality_result_id,
        policy=policy or _policy(),
    )


ORG = _id()
PROJECT = _id()
TASK = _id()


class FakeArtifacts:
    def __init__(self, source: RepairSourceSnapshot) -> None:
        self.template = source
        self.sources = {source.artifact_version_id: source}
        self.promotions: list[str] = []
        self.approvals: list[str] = []
        self.early_stale = False
        self.late_stale = False

    def load_source_exact(self, *, organization_id, project_id, artifact_version_id):
        value = self.sources.get(artifact_version_id)
        if value is None:
            value = replace(
                self.template,
                artifact_version_id=artifact_version_id,
                artifact_content_hash="d" * 64,
                original_branch_id=_id(),
                original_head_version_id=artifact_version_id,
            )
            self.sources[artifact_version_id] = value
        assert value.organization_id == organization_id
        assert value.project_id == project_id
        return value

    def fork_repair_branch(self, *, source, repair_job_id, iteration, actor_id):
        assert source.artifact_version_id in self.sources
        return f"repair-{iteration}-{repair_job_id[:8]}"

    def promote_candidate(self, *, original_source, candidate, repair_job_id, actor_id):
        if self.early_stale:
            raise RepairStaleConflict("stale")
        version_id = _id()
        self.promotions.append(version_id)
        return RepairCandidate(
            artifact_version_id=version_id,
            artifact_content_hash=candidate.artifact_content_hash,
            repair_branch_id=original_source.original_branch_id,
            changed_node_ids=candidate.changed_node_ids,
            metadata={"promotion_state": "STAGED_NOT_HEAD"},
        )

    def approve_promoted_version(self, *, promoted, quality, repair_job_id):
        if self.late_stale:
            raise RepairStaleConflict("stale after validation")
        assert quality.artifact_version_id == promoted.artifact_version_id
        self.approvals.append(promoted.artifact_version_id)
        return promoted.artifact_version_id


class FakeQuality:
    def __init__(self, initial: RepairQualitySnapshot, future=()) -> None:
        self.initial = initial
        self.future = list(future)
        self.evaluated: list[str] = []

    def get_result(self, *, organization_id, quality_result_id):
        assert organization_id == ORG
        assert quality_result_id == self.initial.quality_result_id
        return self.initial

    async def evaluate_candidate(self, *, job, candidate):
        self.evaluated.append(candidate.artifact_version_id)
        if not self.future:
            raise AssertionError("unexpected quality evaluation")
        template = self.future.pop(0)
        return replace(template, artifact_version_id=candidate.artifact_version_id)


class FakeConstraints:
    def __init__(self, *, pre=None, post=None) -> None:
        self.pre = pre or ConstraintCheck(True)
        self.post = post or ConstraintCheck(True)

    async def preflight(self, *, job, plan):
        return self.pre

    async def postflight(self, *, job, plan, candidate):
        return self.post


class FakeExecutor:
    def __init__(
        self,
        *,
        estimate: RepairCostEstimate | None = None,
        actual: str = "0",
        uncertain: bool = False,
        events: list[str] | None = None,
    ) -> None:
        self.estimate_value = estimate or RepairCostEstimate(
            amount_usd=Decimal("0"), provider="internal", model="design-ir"
        )
        self.actual = Decimal(actual)
        self.uncertain = uncertain
        self.execute_count = 0
        self.events = events

    async def estimate(self, *, job, plan):
        return self.estimate_value

    async def execute(self, *, job, plan, repair_branch_id, reservation):
        self.execute_count += 1
        if self.events is not None:
            self.events.append("execute")
        if self.uncertain:
            raise RepairSideEffectUncertain(
                "pending", external_operation_id="edit-pending-1"
            )
        return RepairCandidate(
            artifact_version_id=_id(),
            artifact_content_hash="d" * 64,
            repair_branch_id=repair_branch_id,
            actual_cost_usd=self.actual,
            provider=(self.estimate_value.provider if plan.paid else None),
            model=(self.estimate_value.model if plan.paid else None),
            provider_request_id=("provider-request-1" if plan.paid else None),
        )


class FakeBudget:
    def __init__(self, events: list[str] | None = None) -> None:
        self.reserve_count = 0
        self.release_count = 0
        self.commit_count = 0
        self.events = events

    async def reserve(self, *, job, plan, estimate):
        self.reserve_count += 1
        if self.events is not None:
            self.events.append("reserve")
        return BudgetReservation("reservation-1", estimate.amount_usd)

    async def commit(self, *, job, reservation, candidate, estimate):
        self.commit_count += 1
        if self.events is not None:
            self.events.append("settle")

    async def release(self, *, job, reservation, estimate, reason):
        self.release_count += 1
        if self.events is not None:
            self.events.append("release")


def _engine(source, initial, *, future=(), executor=None, budget=None, constraints=None):
    artifacts = FakeArtifacts(source)
    quality = FakeQuality(initial, future)
    executor = executor or FakeExecutor()
    budget = budget or FakeBudget()
    engine = AutoRepairEngine(
        artifacts=artifacts,
        quality=quality,
        constraints=constraints or FakeConstraints(),
        executor=executor,
        budget=budget,
        repository=InMemoryAutoRepairRepository(),
    )
    return engine, artifacts, quality, executor, budget


def test_start_is_operation_idempotent() -> None:
    source = _source(_id())
    initial = _quality(source.artifact_version_id, directives=(_directive(),))
    engine, *_ = _engine(source, initial)
    spec = _spec(source, initial)
    first = engine.start(spec)
    second = engine.start(spec)
    assert first == second
    assert first.status is RepairLoopStatus.PLANNED


def test_candidate_and_exact_promoted_version_both_must_pass() -> None:
    source = _source(_id())
    initial = _quality(source.artifact_version_id, directives=(_directive(),))
    candidate_pass = _quality(_id(), status="PASS", score=80)
    promoted_pass = _quality(_id(), status="PASS", score=80)
    engine, artifacts, quality, *_ = _engine(
        source, initial, future=(candidate_pass, promoted_pass)
    )
    job = engine.start(_spec(source, initial))
    result = asyncio.run(engine.resume(job.job_id))
    assert result.status is RepairLoopStatus.READY
    assert len(quality.evaluated) == 2
    assert result.final_artifact_version_id == artifacts.promotions[0]
    assert artifacts.approvals == [artifacts.promotions[0]]
    attempt = result.attempts[0]
    assert attempt.decision is RepairAttemptDecision.PROMOTED
    assert attempt.promoted_artifact_version_id == artifacts.promotions[0]
    assert attempt.promotion_quality_result_id == promoted_pass.quality_result_id


def test_candidate_pass_does_not_promote_when_exact_final_quality_fails() -> None:
    source = _source(_id())
    initial = _quality(source.artifact_version_id, directives=(_directive(),))
    engine, artifacts, *_ = _engine(
        source,
        initial,
        future=(
            _quality(_id(), status="PASS", score=80),
            _quality(_id(), status="FAIL_REPAIRABLE", score=79),
        ),
    )
    result = asyncio.run(engine.resume(engine.start(_spec(source, initial)).job_id))
    assert result.status is RepairLoopStatus.REVIEW_REQUIRED
    assert artifacts.approvals == []
    assert result.final_artifact_version_id is None
    assert result.attempts[0].decision is RepairAttemptDecision.PROMOTION_VALIDATION_FAILED


def test_early_and_late_user_edits_become_stale_conflicts() -> None:
    for late in (False, True):
        source = _source(_id())
        initial = _quality(source.artifact_version_id, directives=(_directive(),))
        future = [_quality(_id(), status="PASS", score=80)]
        if late:
            future.append(_quality(_id(), status="PASS", score=80))
        engine, artifacts, *_ = _engine(source, initial, future=tuple(future))
        artifacts.early_stale = not late
        artifacts.late_stale = late
        result = asyncio.run(engine.resume(engine.start(_spec(source, initial)).job_id))
        assert result.status is RepairLoopStatus.STALE_CONFLICT
        assert result.attempts[0].decision is RepairAttemptDecision.PROMOTION_STALE_CONFLICT
        assert result.final_artifact_version_id is None


def test_new_hard_violation_rejects_candidate_and_does_not_change_working_source() -> None:
    source = _source(_id())
    initial = _quality(source.artifact_version_id, directives=(_directive(),))
    after = _quality(_id(), score=75, hard=("QR_UNREADABLE",), directives=(_directive(),))
    engine, *_ = _engine(source, initial, future=(after,))
    result = asyncio.run(engine.resume(engine.start(_spec(source, initial)).job_id))
    assert result.status is RepairLoopStatus.RUNNING
    assert result.working_source.artifact_version_id == source.artifact_version_id
    assert result.attempts[0].decision is RepairAttemptDecision.REJECTED_NEW_HARD_VIOLATION


def test_budget_shortage_without_free_fix_stops_before_execution() -> None:
    source = _source(_id(), artifact_type="RASTER_IMAGE")
    directive = _directive(action="REGENERATE_REGION", code="BACKGROUND_NOISE")
    initial = _quality(source.artifact_version_id, directives=(directive,))
    executor = FakeExecutor(
        estimate=RepairCostEstimate(
            amount_usd=Decimal("1.25"), provider="p", model="m"
        )
    )
    policy = _policy(
        budget="0.50",
        kinds=frozenset({RepairKind.LOCAL_IMAGE_EDIT}),
    )
    engine, *_ = _engine(source, initial, executor=executor)
    result = asyncio.run(engine.resume(engine.start(_spec(source, initial, policy)).job_id))
    assert result.status is RepairLoopStatus.BUDGET_EXHAUSTED
    assert executor.execute_count == 0


def test_paid_repair_reserves_before_execution_and_settles_after() -> None:
    events: list[str] = []
    source = _source(_id(), artifact_type="RASTER_IMAGE")
    initial = _quality(
        source.artifact_version_id,
        directives=(_directive(action="REGENERATE_REGION", code="BACKGROUND_NOISE"),),
    )
    executor = FakeExecutor(
        estimate=RepairCostEstimate(
            amount_usd=Decimal("0.50"), provider="p", model="m"
        ),
        actual="0.40",
        events=events,
    )
    budget = FakeBudget(events)
    engine, *_ = _engine(
        source,
        initial,
        future=(_quality(_id(), status="FAIL_REPAIRABLE", score=65, directives=()),),
        executor=executor,
        budget=budget,
    )
    result = asyncio.run(engine.resume(engine.start(_spec(source, initial)).job_id))
    assert events[:3] == ["reserve", "execute", "settle"]
    assert result.spent_usd == Decimal("0.40")


def test_uncertain_paid_side_effect_is_not_released_or_replayed() -> None:
    source = _source(_id(), artifact_type="RASTER_IMAGE")
    initial = _quality(
        source.artifact_version_id,
        directives=(_directive(action="REGENERATE_REGION", code="BACKGROUND_NOISE"),),
    )
    executor = FakeExecutor(
        estimate=RepairCostEstimate(
            amount_usd=Decimal("0.50"), provider="p", model="m"
        ),
        uncertain=True,
    )
    budget = FakeBudget()
    engine, *_ = _engine(source, initial, executor=executor, budget=budget)
    job = engine.start(_spec(source, initial))
    result = asyncio.run(engine.resume(job.job_id))
    assert result.status is RepairLoopStatus.REVIEW_REQUIRED
    assert result.attempts[0].decision is RepairAttemptDecision.COST_RECONCILIATION_REQUIRED
    assert budget.reserve_count == 1
    assert budget.release_count == 0
    assert budget.commit_count == 0
    replay = asyncio.run(engine.resume(job.job_id))
    assert replay == result
    assert executor.execute_count == 1


def test_actual_cost_overrun_stops_loop() -> None:
    source = _source(_id(), artifact_type="RASTER_IMAGE")
    initial = _quality(
        source.artifact_version_id,
        directives=(_directive(action="REGENERATE_REGION", code="BACKGROUND_NOISE"),),
    )
    executor = FakeExecutor(
        estimate=RepairCostEstimate(
            amount_usd=Decimal("0.40"), provider="p", model="m"
        ),
        actual="0.80",
    )
    engine, *_ = _engine(source, initial, executor=executor)
    policy = _policy(
        budget="0.50",
        kinds=frozenset({RepairKind.LOCAL_IMAGE_EDIT}),
    )
    result = asyncio.run(engine.resume(engine.start(_spec(source, initial, policy)).job_id))
    assert result.status is RepairLoopStatus.BUDGET_EXHAUSTED
    assert result.spent_usd == Decimal("0.80")


def test_same_failed_directive_is_not_executed_twice() -> None:
    directive = _directive()
    source = _source(_id())
    initial = _quality(source.artifact_version_id, directives=(directive,))
    after = _quality(_id(), score=54, directives=(directive,))
    engine, *_ = _engine(source, initial, future=(after,))
    job = engine.start(_spec(source, initial))
    first = asyncio.run(engine.resume(job.job_id))
    assert first.status is RepairLoopStatus.RUNNING
    second = asyncio.run(engine.resume(job.job_id))
    assert second.status is RepairLoopStatus.REVIEW_REQUIRED
    assert len(second.attempts) == 1
