from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    ConstraintViolation,
    RuntimeConstraint,
    ValidationAdapters,
    ValidationMetrics,
    ValidationPhase,
    ValidationPolicy,
    ValidationReport,
)
from .impact import impact_set
from .projection import project_operation
from .validators import relevant_specs

_LOCKED_OPERATION_TYPES: dict[str, frozenset[str]] = {
    "LOCK_POSITION": frozenset({"MOVE_NODE"}),
    "LOCK_SIZE": frozenset({"RESIZE_NODE"}),
    "LOCK_ROTATION": frozenset({"ROTATE_NODE"}),
    "LOCK_TRANSFORM": frozenset({"MOVE_NODE", "RESIZE_NODE", "ROTATE_NODE"}),
    "LOCK_LAYER_ORDER": frozenset({"REORDER_NODE"}),
    "LOCK_PARENT": frozenset({"REPARENT_NODE"}),
    "LOCK_CONTENT": frozenset({"SET_TEXT", "REPLACE_ASSET", "DELETE_NODE"}),
    "LOCK_TEXT": frozenset({"SET_TEXT"}),
    "LOCK_ASSET": frozenset({"REPLACE_ASSET"}),
    "LOCK_STYLE": frozenset({"APPLY_STYLE", "SET_PROPERTY"}),
}


def _lock_applies(constraint: RuntimeConstraint, operation: Mapping[str, Any] | None) -> bool:
    if operation is None:
        return False
    allowed = _LOCKED_OPERATION_TYPES.get(constraint.type)
    return allowed is not None and operation.get("type") in allowed


def _health_score(
    constraints: tuple[RuntimeConstraint, ...], violations: tuple[ConstraintViolation, ...]
) -> float:
    weights = {"HARD": 5.0, "SOFT": 2.0, "ADVISORY": 1.0}
    active = [item for item in constraints if item.active]
    denominator = sum(weights[item.severity] for item in active)
    if denominator == 0:
        return 100.0
    failed_ids = {item.constraint_id for item in violations}
    penalty = sum(weights[item.severity] for item in active if item.constraint_id in failed_ids)
    return round(max(0.0, 100.0 * (1.0 - penalty / denominator)), 4)


def _sort_violations(values: list[ConstraintViolation]) -> tuple[ConstraintViolation, ...]:
    dedup = {item.violation_id: item for item in values}
    return tuple(
        sorted(
            dedup.values(),
            key=lambda item: (
                item.constraint_id,
                item.validator,
                item.affected_node_ids,
                item.violation_id,
            ),
        )
    )


def validate_constraints(
    document: Mapping[str, Any],
    constraints: tuple[RuntimeConstraint, ...],
    *,
    operation: Mapping[str, Any] | None = None,
    phase: ValidationPhase = "preflight",
    adapters: ValidationAdapters | None = None,
    policy: ValidationPolicy | None = None,
    force_full: bool = False,
) -> ValidationReport:
    active_policy = policy or ValidationPolicy()
    active_adapters = adapters or ValidationAdapters()
    candidate = project_operation(document, operation) if operation is not None else dict(document)
    impact, fallback = impact_set(
        candidate,
        operation,
        constraints,
        active_policy,
        force_full=force_full or phase == "export",
    )
    violations: list[ConstraintViolation] = []
    validators_run: set[str] = set()
    for constraint in sorted(
        (item for item in constraints if item.active), key=lambda item: item.constraint_id
    ):
        for spec in relevant_specs(constraint):
            if spec.name == "LockedRegionValidator" and not _lock_applies(
                constraint, operation
            ):
                continue
            if spec.name == "ExportDimensionValidator" and phase != "export":
                continue
            validators_run.add(spec.name)
            violations.extend(
                spec.fn(candidate, constraint, impact, active_adapters, active_policy)
            )
    ordered = _sort_violations(violations)
    blocking = sum(1 for item in ordered if item.blocking)
    unavailable = any(item.unavailable for item in ordered)
    if blocking:
        status = "BLOCKED"
    elif unavailable:
        status = "VALIDATION_UNAVAILABLE"
    elif ordered:
        status = "WARN"
    else:
        status = "PASS"
    return ValidationReport(
        status=status,
        violations=ordered,
        hard_pass=blocking == 0,
        health_score=_health_score(constraints, ordered),
        metrics=ValidationMetrics(
            validators_run=tuple(sorted(validators_run)),
            nodes_scanned=len(impact),
            violations_count=len(ordered),
            blocking_count=blocking,
            fallback_full_scan=fallback,
        ),
    )


def validate_batch(
    document: Mapping[str, Any],
    constraints: tuple[RuntimeConstraint, ...],
    operations: tuple[Mapping[str, Any], ...],
    *,
    adapters: ValidationAdapters | None = None,
    policy: ValidationPolicy | None = None,
) -> ValidationReport:
    working: Mapping[str, Any] = document
    all_violations: list[ConstraintViolation] = []
    validators: set[str] = set()
    nodes_scanned = 0
    fallback = False
    for operation in operations:
        report = validate_constraints(
            working,
            constraints,
            operation=operation,
            adapters=adapters,
            policy=policy,
        )
        all_violations.extend(report.violations)
        validators.update(report.metrics.validators_run)
        nodes_scanned += report.metrics.nodes_scanned
        fallback = fallback or report.metrics.fallback_full_scan
        working = project_operation(working, operation)
    ordered = _sort_violations(all_violations)
    blocking = sum(1 for item in ordered if item.blocking)
    unavailable = any(item.unavailable for item in ordered)
    if blocking:
        status = "BLOCKED"
    elif unavailable:
        status = "VALIDATION_UNAVAILABLE"
    elif ordered:
        status = "WARN"
    else:
        status = "PASS"
    return ValidationReport(
        status=status,
        violations=ordered,
        hard_pass=blocking == 0,
        health_score=_health_score(constraints, ordered),
        metrics=ValidationMetrics(
            validators_run=tuple(sorted(validators)),
            nodes_scanned=nodes_scanned,
            violations_count=len(ordered),
            blocking_count=blocking,
            fallback_full_scan=fallback,
        ),
    )


def validate_export(
    document: Mapping[str, Any],
    constraints: tuple[RuntimeConstraint, ...],
    *,
    adapters: ValidationAdapters | None = None,
    policy: ValidationPolicy | None = None,
) -> ValidationReport:
    return validate_constraints(
        document,
        constraints,
        phase="export",
        adapters=adapters,
        policy=policy,
        force_full=True,
    )


def to_ir_preflight_issues(report: ValidationReport) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "code": "IR_CONSTRAINT_FAILED",
            "message": item.message,
            "node_ids": list(item.affected_node_ids),
        }
        for item in report.violations
        if item.blocking
    )
