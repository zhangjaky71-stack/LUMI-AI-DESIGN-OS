from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .model import Constraint, OverrideAudit, PostflightEvidence, PostflightResult, Violation
from .precedence import detect_conflicts, effective_constraints
from .registry import EVALUATORS


def _override_active(constraint: Constraint, overrides: Mapping[str, OverrideAudit]) -> bool:
    audit = overrides.get(constraint.id)
    return bool(
        audit
        and audit.authorized is True
        and audit.constraint_id == constraint.id
        and constraint.source != "SAFETY_SYSTEM"
        and constraint.override_policy == "AUTHORIZED"
    )


def _violation(
    constraint: Constraint,
    *,
    target_id: str | None,
    code: str,
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    repair_hint: Mapping[str, Any] | None = None,
    severity: str | None = None,
) -> Violation:
    return Violation(
        constraint_id=constraint.id,
        type=constraint.type,
        severity=severity or constraint.severity,  # type: ignore[arg-type]
        phase="POSTFLIGHT",
        target_id=target_id,
        expected=expected,
        actual=actual,
        message_code=code,
        repair_hint=repair_hint or {},
        overrideable=constraint.source != "SAFETY_SYSTEM" and constraint.override_policy == "AUTHORIZED",
    )


def _target_id(constraint: Constraint) -> str | None:
    if constraint.scope.node_ids:
        return constraint.scope.node_ids[0]
    if constraint.scope.frame_ids:
        return constraint.scope.frame_ids[0]
    return None


def _threshold(constraint: Constraint, evidence: PostflightEvidence) -> tuple[bool, Mapping[str, Any], Mapping[str, Any], str]:
    actual = evidence.actual
    if constraint.type == "REQUIRE_CONTRAST":
        minimum = float(constraint.parameters.get("min_ratio", 4.5))
        value = float(actual.get("ratio", 0))
        return value >= minimum, {"min_ratio": minimum}, {"ratio": value}, "CONSTRAINT_CONTRAST_TOO_LOW"
    if constraint.type == "REQUIRE_TEXT_READABILITY":
        minimum = float(constraint.parameters.get("min_score", 0.7))
        value = float(actual.get("score", 0))
        return value >= minimum, {"min_score": minimum}, {"score": value}, "CONSTRAINT_TEXT_NOT_READABLE"
    if constraint.type in {"REQUIRE_BRAND_COMPLIANCE", "LOCK_BRAND"}:
        minimum = float(constraint.parameters.get("min_score", 0.8))
        value = float(actual.get("score", 0))
        return value >= minimum, {"min_score": minimum}, {"score": value}, "CONSTRAINT_BRAND_COMPLIANCE_FAILED"
    if constraint.type in {"REQUIRE_IDENTITY_SCORE", "LOCK_IDENTITY"}:
        minimum = float(constraint.parameters.get("min_score", 0.85))
        value = float(actual.get("score", 0))
        return value >= minimum, {"min_score": minimum}, {"score": value}, "CONSTRAINT_IDENTITY_SCORE_TOO_LOW"
    return evidence.passed, {"passed": True}, dict(actual), "CONSTRAINT_POSTFLIGHT_FAILED"


def _evaluate(
    constraint: Constraint,
    evidence: PostflightEvidence,
) -> tuple[list[tuple[Violation, bool]], list[Violation]]:
    spec = EVALUATORS[constraint.type]
    hard_or_soft: list[tuple[Violation, bool]] = []
    warnings: list[Violation] = []
    target_id = _target_id(constraint)

    if evidence.kind != spec.evidence:
        hard_or_soft.append(
            (
                _violation(
                    constraint,
                    target_id=target_id,
                    code="CONSTRAINT_EVIDENCE_KIND_MISMATCH",
                    expected={"evidence_kind": spec.evidence},
                    actual={"evidence_kind": evidence.kind},
                    repair_hint={"action": "run_correct_validator"},
                ),
                False,
            )
        )
        return hard_or_soft, warnings

    if spec.evaluator == "qr_scannability":
        actual = evidence.actual
        core_ok = all(actual.get(key) is True for key in ("detected", "decoded", "payload_match"))
        if not core_ok:
            hard_or_soft.append(
                (
                    _violation(
                        constraint,
                        target_id=target_id,
                        code="CONSTRAINT_QR_NOT_SCANNABLE",
                        expected={"detected": True, "decoded": True, "payload_match": True},
                        actual=dict(actual),
                        repair_hint={"action": "repair_qr_and_revalidate"},
                    ),
                    evidence.repairable,
                )
            )
            return hard_or_soft, warnings
        if actual.get("quiet_zone_ok") is False or actual.get("size_ok") is False:
            warnings.append(
                _violation(
                    constraint,
                    target_id=target_id,
                    code="CONSTRAINT_QR_QUIET_ZONE_WARNING",
                    expected={"quiet_zone_ok": True, "size_ok": True},
                    actual=dict(actual),
                    repair_hint={"action": "increase_qr_quiet_zone_or_size"},
                    severity="SOFT",
                )
            )
        return hard_or_soft, warnings

    if spec.evaluator == "resolution":
        actual = evidence.actual
        min_width = int(constraint.parameters.get("min_width", 1))
        min_height = int(constraint.parameters.get("min_height", 1))
        width = int(actual.get("width", 0))
        height = int(actual.get("height", 0))
        if width < min_width or height < min_height:
            hard_or_soft.append(
                (
                    _violation(
                        constraint,
                        target_id=target_id,
                        code="CONSTRAINT_RESOLUTION_TOO_LOW",
                        expected={"min_width": min_width, "min_height": min_height},
                        actual={"width": width, "height": height},
                        repair_hint={"action": "regenerate_or_upscale"},
                    ),
                    evidence.repairable,
                )
            )
        return hard_or_soft, warnings

    if spec.evaluator == "protected_region":
        max_diff = float(constraint.parameters.get("max_diff", 0.01))
        diff = float(evidence.actual.get("diff_ratio", 1))
        if diff > max_diff:
            hard_or_soft.append(
                (
                    _violation(
                        constraint,
                        target_id=target_id,
                        code="CONSTRAINT_PROTECTED_REGION_DIFF_EXCEEDED",
                        expected={"max_diff": max_diff},
                        actual={"diff_ratio": diff},
                        repair_hint={"action": "restore_protected_region"},
                    ),
                    evidence.repairable,
                )
            )
        return hard_or_soft, warnings

    passed, expected, actual, code = _threshold(constraint, evidence)
    if not passed:
        hard_or_soft.append(
            (
                _violation(
                    constraint,
                    target_id=target_id,
                    code=code,
                    expected=expected,
                    actual=actual,
                    repair_hint={"action": "repair_and_revalidate"},
                ),
                evidence.repairable,
            )
        )
    return hard_or_soft, warnings


def postflight(
    constraints: Iterable[Constraint],
    evidence_by_constraint: Mapping[str, PostflightEvidence],
    *,
    overrides: Mapping[str, OverrideAudit] | None = None,
) -> PostflightResult:
    override_map = overrides or {}
    all_constraints = tuple(constraints)
    conflict_violations = detect_conflicts(all_constraints)

    failures: list[tuple[Violation, bool, Constraint | None]] = []
    warnings: list[Violation] = []
    for conflict in conflict_violations:
        if conflict.severity == "HARD":
            failures.append((conflict, False, None))
        else:
            warnings.append(conflict)

    for constraint in effective_constraints(all_constraints):
        if _override_active(constraint, override_map):
            continue
        spec = EVALUATORS.get(constraint.type)
        if spec is None or spec.phase not in {"POSTFLIGHT", "BOTH"}:
            continue
        evidence = evidence_by_constraint.get(constraint.id)
        if evidence is None:
            violation = _violation(
                constraint,
                target_id=_target_id(constraint),
                code="CONSTRAINT_EVIDENCE_MISSING",
                expected={"evidence_kind": spec.evidence},
                actual={"present": False},
                repair_hint={"action": "run_required_validator"},
            )
            if constraint.severity == "HARD":
                failures.append((violation, False, constraint))
            else:
                warnings.append(violation)
            continue

        evaluated, local_warnings = _evaluate(constraint, evidence)
        warnings.extend(local_warnings)
        for violation, repairable in evaluated:
            if violation.severity == "HARD":
                failures.append((violation, repairable, constraint))
            else:
                warnings.append(violation)

    if not failures:
        return PostflightResult("PASS", (), tuple(warnings))

    hard_violations = tuple(item[0] for item in failures)
    all_repairable = all(item[1] for item in failures)
    has_safety = any(item[2] is not None and item[2].source == "SAFETY_SYSTEM" for item in failures)
    outcome = "FAIL_REPAIRABLE" if all_repairable and not has_safety else "FAIL_HARD"
    return PostflightResult(outcome, hard_violations, tuple(warnings))
