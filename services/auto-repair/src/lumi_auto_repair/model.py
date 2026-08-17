from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class RepairKind(StrEnum):
    STRUCTURAL_DESIGN_OP = "STRUCTURAL_DESIGN_OP"
    LOCAL_IMAGE_EDIT = "LOCAL_IMAGE_EDIT"
    REGENERATE_ELEMENT = "REGENERATE_ELEMENT"
    REGENERATE_ARTIFACT = "REGENERATE_ARTIFACT"
    COPY_TYPOGRAPHY_FIX = "COPY_TYPOGRAPHY_FIX"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class RepairLoopStatus(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    STALE_CONFLICT = "STALE_CONFLICT"
    CANCELLED = "CANCELLED"


class RepairAttemptDecision(StrEnum):
    ACCEPTED_INTERMEDIATE = "ACCEPTED_INTERMEDIATE"
    PROMOTED = "PROMOTED"
    REJECTED_PREFLIGHT = "REJECTED_PREFLIGHT"
    REJECTED_POSTFLIGHT = "REJECTED_POSTFLIGHT"
    REJECTED_NEW_HARD_VIOLATION = "REJECTED_NEW_HARD_VIOLATION"
    REJECTED_REGRESSION = "REJECTED_REGRESSION"
    REJECTED_INSUFFICIENT_GAIN = "REJECTED_INSUFFICIENT_GAIN"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class RepairDirective:
    directive_id: str
    source_violation_id: str
    dimension: str
    severity: str
    blocking: bool
    action_type: str
    target: str
    parameters: dict[str, Any] = field(default_factory=dict)
    protected_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            (
                self.directive_id,
                self.source_violation_id,
                self.dimension,
                self.severity,
                self.action_type,
                self.target,
            )
        ):
            raise ValueError("REPAIR_DIRECTIVE_IDENTITY_REQUIRED")


@dataclass(frozen=True, slots=True)
class RepairQualitySnapshot:
    quality_result_id: str
    artifact_version_id: str
    status: str
    overall_score: float
    overall_confidence: float
    hard_violation_codes: tuple[str, ...]
    directives: tuple[RepairDirective, ...]
    profile_id: str
    profile_version: int
    profile_hash: str

    def __post_init__(self) -> None:
        if not 0 <= self.overall_score <= 100:
            raise ValueError("REPAIR_QUALITY_SCORE_INVALID")
        if not 0 <= self.overall_confidence <= 1:
            raise ValueError("REPAIR_QUALITY_CONFIDENCE_INVALID")
        _sha256(self.profile_hash, "repair quality profile hash")


@dataclass(frozen=True, slots=True)
class RepairSourceSnapshot:
    organization_id: str
    project_id: str
    artifact_id: str
    artifact_version_id: str
    artifact_content_hash: str
    artifact_type: str
    original_branch_id: str
    original_head_version_id: str
    design_document_id: str | None = None
    design_document_version_id: str | None = None
    constraint_snapshot_hash: str | None = None
    protected_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _sha256(self.artifact_content_hash, "repair source content hash")
        if self.constraint_snapshot_hash is not None:
            _sha256(
                self.constraint_snapshot_hash,
                "repair constraint snapshot hash",
            )
        if not all(
            (
                self.organization_id,
                self.project_id,
                self.artifact_id,
                self.artifact_version_id,
                self.artifact_type,
                self.original_branch_id,
                self.original_head_version_id,
            )
        ):
            raise ValueError("REPAIR_SOURCE_IDENTITY_REQUIRED")


@dataclass(frozen=True, slots=True)
class RepairPolicySnapshot:
    policy_id: str
    version: int
    max_iterations: int
    max_total_cost_usd: Decimal
    minimum_expected_gain: float
    max_score_regression: float
    allowed_kinds: frozenset[RepairKind]
    allow_paid_repairs: bool = True

    def __post_init__(self) -> None:
        if not self.policy_id or self.version < 1:
            raise ValueError("REPAIR_POLICY_IDENTITY_REQUIRED")
        if self.max_iterations < 1 or self.max_iterations > 3:
            raise ValueError("REPAIR_POLICY_ITERATIONS_INVALID")
        if self.max_total_cost_usd < 0:
            raise ValueError("REPAIR_POLICY_BUDGET_INVALID")
        if not 0 <= self.minimum_expected_gain <= 100:
            raise ValueError("REPAIR_POLICY_GAIN_INVALID")
        if not 0 <= self.max_score_regression <= 100:
            raise ValueError("REPAIR_POLICY_REGRESSION_INVALID")
        if not self.allowed_kinds:
            raise ValueError("REPAIR_POLICY_KINDS_REQUIRED")

    def semantic_hash(self) -> str:
        return _canonical_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class AutoRepairTaskSpec:
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    requested_by: str
    source_artifact_version_id: str
    quality_result_id: str
    policy: RepairPolicySnapshot

    def __post_init__(self) -> None:
        if not all(
            (
                self.organization_id,
                self.project_id,
                self.task_id,
                self.operation_id,
                self.requested_by,
                self.source_artifact_version_id,
                self.quality_result_id,
            )
        ):
            raise ValueError("REPAIR_TASK_IDENTITY_REQUIRED")

    def semantic_hash(self) -> str:
        return _canonical_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class RepairPlan:
    iteration: int
    kind: RepairKind
    directives: tuple[RepairDirective, ...]
    expected_gain: float
    estimated_cost_usd: Decimal
    paid: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.iteration < 1:
            raise ValueError("REPAIR_PLAN_ITERATION_INVALID")
        if self.estimated_cost_usd < 0:
            raise ValueError("REPAIR_PLAN_COST_INVALID")
        if not 0 <= self.expected_gain <= 100:
            raise ValueError("REPAIR_PLAN_GAIN_INVALID")
        if self.kind is RepairKind.MANUAL_REVIEW and self.paid:
            raise ValueError("REPAIR_MANUAL_REVIEW_CANNOT_BE_PAID")
        if self.kind is not RepairKind.MANUAL_REVIEW and not self.directives:
            raise ValueError("REPAIR_PLAN_DIRECTIVES_REQUIRED")


@dataclass(frozen=True, slots=True)
class ConstraintCheck:
    passed: bool
    blocking_codes: tuple[str, ...] = ()
    unavailable: bool = False
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    reservation_id: str
    amount_usd: Decimal
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    artifact_version_id: str
    artifact_content_hash: str
    repair_branch_id: str
    changed_node_ids: tuple[str, ...] = ()
    actual_cost_usd: Decimal = Decimal("0")
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _sha256(self.artifact_content_hash, "repair candidate content hash")
        if self.actual_cost_usd < 0:
            raise ValueError("REPAIR_CANDIDATE_COST_INVALID")


@dataclass(frozen=True, slots=True)
class RepairAttempt:
    iteration: int
    source_artifact_version_id: str
    before_quality_result_id: str
    before_score: float
    plan: RepairPlan
    candidate: RepairCandidate | None
    after_quality_result_id: str | None
    after_score: float | None
    score_delta: float | None
    decision: RepairAttemptDecision
    preflight: ConstraintCheck | None = None
    postflight: ConstraintCheck | None = None
    reservation_id: str | None = None
    actual_cost_usd: Decimal = Decimal("0")
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AutoRepairJob:
    job_id: str
    spec: AutoRepairTaskSpec
    status: RepairLoopStatus
    original_source: RepairSourceSnapshot
    working_source: RepairSourceSnapshot
    current_quality: RepairQualitySnapshot
    attempts: tuple[RepairAttempt, ...] = ()
    spent_usd: Decimal = Decimal("0")
    final_artifact_version_id: str | None = None
    reason_codes: tuple[str, ...] = ()

    @property
    def remaining_budget_usd(self) -> Decimal:
        value = self.spec.policy.max_total_cost_usd - self.spent_usd
        return max(value, Decimal("0"))

    @property
    def next_iteration(self) -> int:
        return len(self.attempts) + 1


def _sha256(value: str, label: str) -> None:
    if len(value) != 64 or value.lower() != value:
        raise ValueError(f"{label} must be lowercase sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be lowercase sha256") from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, frozenset):
        return sorted(_jsonable(item) for item in value)
    if isinstance(value, dict):
        return {
            str(key.value if isinstance(key, StrEnum) else key): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
