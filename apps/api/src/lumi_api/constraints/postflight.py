# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from .models import (
    Constraint,
    ConstraintOverride,
    ConstraintSet,
    ConstraintViolation,
    PostflightObservation,
    PostflightResult,
    constraint_snapshot_hash,
)
from .preflight import resolve_active_constraints
from .registry import EVALUATOR_CONTRACTS


def _matches(constraint: Constraint, observation: PostflightObservation) -> bool:
    contract = EVALUATOR_CONTRACTS[constraint.type]
    if contract.postflight_observation_kind != observation.kind:
        return False
    if constraint.scope.node_ids:
        return observation.target_id in constraint.scope.node_ids
    return True


def _metric_bool(metrics: dict[str, Any], key: str) -> bool | None:
    value = metrics.get(key)
    return value if isinstance(value, bool) else None


def _metric_number(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _evaluate_one(
    constraint: Constraint,
    observation: PostflightObservation,
) -> tuple[bool, bool, dict[str, Any], dict[str, Any], str]:
    metrics = observation.metrics
    params = constraint.parameters
    ctype = constraint.type

    if ctype.startswith("LOCK_"):
        key = ctype.removeprefix("LOCK_").lower() + "_unchanged"
        passed = _metric_bool(metrics, key)
        return (
            passed is True,
            False,
            {key: True},
            {key: passed},
            f"CONSTRAINT_{ctype}_POSTFLIGHT",
        )
    if ctype == "PROTECT_REGION":
        score = _metric_number(metrics, "difference_score")
        threshold = float(params.get("max_difference", 0.02))
        return (
            score is not None and score <= threshold,
            True,
            {"difference_score_max": threshold},
            {"difference_score": score},
            "CONSTRAINT_PROTECTED_REGION_CHANGED",
        )
    if ctype == "MUST_STAY_INSIDE":
        value = _metric_bool(metrics, "inside")
        return (
            value is True,
            True,
            {"inside": True},
            {"inside": value},
            "CONSTRAINT_OUTSIDE_REQUIRED_REGION",
        )
    if ctype == "MUST_NOT_OVERLAP":
        value = _metric_bool(metrics, "overlap")
        return (
            value is False,
            True,
            {"overlap": False},
            {"overlap": value},
            "CONSTRAINT_FORBIDDEN_OVERLAP",
        )
    if ctype == "MIN_MARGIN":
        actual = _metric_number(metrics, "margin")
        minimum = float(params.get("min_margin", 0.0))
        return (
            actual is not None and actual >= minimum,
            True,
            {"margin_min": minimum},
            {"margin": actual},
            "CONSTRAINT_MIN_MARGIN",
        )
    if ctype == "SAFE_AREA":
        value = _metric_bool(metrics, "inside_safe_area")
        return (
            value is True,
            True,
            {"inside_safe_area": True},
            {"inside_safe_area": value},
            "CONSTRAINT_SAFE_AREA",
        )
    if ctype == "REQUIRE_CONTRAST":
        ratio = _metric_number(metrics, "contrast_ratio")
        minimum = float(params.get("min_ratio", 4.5))
        return (
            ratio is not None and ratio >= minimum,
            True,
            {"contrast_ratio_min": minimum},
            {"contrast_ratio": ratio},
            "CONSTRAINT_CONTRAST_LOW",
        )
    if ctype == "REQUIRE_SCANNABILITY":
        required = {"detected": True, "decoded": True, "payload_match": True}
        core_pass = all(
            _metric_bool(metrics, key) is expected
            for key, expected in required.items()
        )
        return (
            core_pass,
            False,
            required,
            {
                key: metrics.get(key)
                for key in (*required, "quiet_zone_ok", "module_size_ok")
            },
            "CONSTRAINT_QR_NOT_SCANNABLE",
        )
    if ctype == "REQUIRE_TEXT_READABILITY":
        score = _metric_number(metrics, "readability_score")
        minimum = float(params.get("min_score", 0.8))
        return (
            score is not None and score >= minimum,
            True,
            {"readability_score_min": minimum},
            {"readability_score": score},
            "CONSTRAINT_TEXT_READABILITY",
        )
    if ctype == "REQUIRE_BRAND_COMPLIANCE":
        value = _metric_bool(metrics, "compliant")
        return (
            value is True,
            True,
            {"compliant": True},
            {"compliant": value},
            "CONSTRAINT_BRAND_NONCOMPLIANT",
        )
    if ctype == "REQUIRE_RESOLUTION":
        width = _metric_number(metrics, "width")
        height = _metric_number(metrics, "height")
        min_width = float(params.get("min_width", 1))
        min_height = float(params.get("min_height", 1))
        passed = (
            width is not None
            and height is not None
            and width >= min_width
            and height >= min_height
        )
        return (
            passed,
            True,
            {"min_width": min_width, "min_height": min_height},
            {"width": width, "height": height},
            "CONSTRAINT_RESOLUTION_LOW",
        )
    if ctype == "REQUIRE_IDENTITY_SCORE":
        score = _metric_number(metrics, "identity_score")
        minimum = float(params.get("min_score", 0.9))
        return (
            score is not None and score >= minimum,
            True,
            {"identity_score_min": minimum},
            {"identity_score": score},
            "CONSTRAINT_IDENTITY_SCORE_LOW",
        )
    raise AssertionError(f"no postflight evaluator for {ctype}")


def evaluate_postflight(
    constraint_set: ConstraintSet,
    observations: Iterable[PostflightObservation],
    *,
    overrides: Iterable[ConstraintOverride] = (),
) -> PostflightResult:
    snapshot = constraint_snapshot_hash(constraint_set)
    resolved, conflicts = resolve_active_constraints(constraint_set)
    observation_list = tuple(observations)
    override_by_constraint = {item.constraint_id: item for item in overrides}
    violations: list[ConstraintViolation] = []
    warnings: list[ConstraintViolation] = []
    applied_overrides: list[UUID] = []

    for conflict in conflicts:
        violations.append(
            ConstraintViolation(
                constraint_id=conflict.constraint_ids[0],
                type=conflict.type,
                severity="HARD",
                phase="postflight",
                message_code=conflict.message_code,
                expected={"same_precedence": "single deterministic rule"},
                actual={
                    "conflicting_constraint_ids": [
                        str(item) for item in conflict.constraint_ids
                    ]
                },
            )
        )

    for constraint in resolved:
        contract = EVALUATOR_CONTRACTS[constraint.type]
        if "postflight" not in contract.stages:
            continue
        override = override_by_constraint.get(constraint.id)
        if override is not None and constraint.source != "SAFETY_SYSTEM":
            applied_overrides.append(override.override_id)
            continue
        matching = [
            item for item in observation_list if _matches(constraint, item)
        ]
        if not matching:
            item = ConstraintViolation(
                constraint_id=constraint.id,
                type=constraint.type,
                severity=constraint.severity,
                target_id=(
                    constraint.scope.node_ids[0]
                    if constraint.scope.node_ids
                    else None
                ),
                phase="postflight",
                expected={
                    "observation_kind": contract.postflight_observation_kind
                },
                actual={"observation": None},
                message_code="CONSTRAINT_POSTFLIGHT_OBSERVATION_MISSING",
                repair_hint={
                    "collect_required_observation": (
                        contract.postflight_observation_kind
                    )
                },
                repairable=True,
            )
            if constraint.severity == "HARD":
                violations.append(item)
            else:
                warnings.append(item)
            continue

        for observation in matching:
            passed, repairable, expected, actual, code = _evaluate_one(
                constraint,
                observation,
            )
            if passed:
                if constraint.type == "REQUIRE_SCANNABILITY":
                    for advisory_key in ("quiet_zone_ok", "module_size_ok"):
                        if observation.metrics.get(advisory_key) is False:
                            warnings.append(
                                ConstraintViolation(
                                    constraint_id=constraint.id,
                                    type=constraint.type,
                                    severity="ADVISORY",
                                    target_id=observation.target_id,
                                    phase="postflight",
                                    expected={advisory_key: True},
                                    actual={advisory_key: False},
                                    message_code=(
                                        f"CONSTRAINT_QR_{advisory_key.upper()}_WARNING"
                                    ),
                                    repairable=True,
                                )
                            )
                continue
            violation = ConstraintViolation(
                constraint_id=constraint.id,
                type=constraint.type,
                severity=constraint.severity,
                target_id=observation.target_id,
                phase="postflight",
                expected=expected,
                actual=actual,
                message_code=code,
                repair_hint={"retry_or_repair": repairable},
                repairable=repairable,
            )
            if constraint.severity == "HARD":
                violations.append(violation)
            else:
                warnings.append(violation)

    if violations:
        status = "FAIL_HARD"
        can_approve = False
    elif warnings:
        status = "FAIL_REPAIRABLE"
        can_approve = True
    else:
        status = "PASS"
        can_approve = True
    return PostflightResult(
        status=status,
        violations=tuple(violations),
        warnings=tuple(warnings),
        constraint_snapshot_hash=snapshot,
        applied_override_ids=tuple(sorted(set(applied_overrides), key=str)),
        can_approve=can_approve,
    )
