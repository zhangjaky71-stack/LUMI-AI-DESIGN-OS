from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

Severity = Literal["HARD", "SOFT", "ADVISORY"]
ValidationPhase = Literal["preflight", "postflight", "export"]
ValidationStatus = Literal["PASS", "WARN", "BLOCKED", "VALIDATION_UNAVAILABLE"]

P0_VALIDATORS: tuple[str, ...] = (
    "BoundsValidator",
    "SafeAreaValidator",
    "LockedRegionValidator",
    "TextOverflowValidator",
    "FontSizeValidator",
    "AspectRatioValidator",
    "ContrastValidator",
    "ProtectedRegionValidator",
    "QRValidator",
    "BrandTokenValidator",
    "IdentityPreservationValidator",
    "ExportDimensionValidator",
)


@dataclass(frozen=True, slots=True)
class RuntimeScope:
    node_ids: tuple[str, ...] = ()
    semantic_tags: tuple[str, ...] = ()
    region: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeConstraint:
    constraint_id: str
    type: str
    severity: Severity
    scope: RuntimeScope = field(default_factory=RuntimeScope)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    active: bool = True


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    incremental_full_scan_ratio: float = 0.40
    incremental_full_scan_node_limit: int = 500
    unavailable_hard_blocks: bool = True
    max_auto_fix_rounds: int = 1

    def __post_init__(self) -> None:
        if not 0 < self.incremental_full_scan_ratio <= 1:
            raise ValueError("CONSTRAINT_VALIDATOR_SCAN_RATIO_INVALID")
        if self.incremental_full_scan_node_limit < 1:
            raise ValueError("CONSTRAINT_VALIDATOR_SCAN_LIMIT_INVALID")
        if self.max_auto_fix_rounds != 1:
            raise ValueError("CONSTRAINT_VALIDATOR_REPAIR_LOOP_FORBIDDEN")


TextMeasure = Callable[[Mapping[str, Any]], Mapping[str, float]]
QrDecode = Callable[[Mapping[str, Any]], bool]
IdentityScore = Callable[[Mapping[str, Any]], float | None]


@dataclass(frozen=True, slots=True)
class ValidationAdapters:
    text_measure: TextMeasure | None = None
    qr_decode: QrDecode | None = None
    identity_score: IdentityScore | None = None


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    violation_id: str
    constraint_id: str
    type: str
    validator: str
    severity: Severity
    affected_node_ids: tuple[str, ...]
    message: str
    measured_value: Any = None
    expected_value: Any = None
    suggested_fix_operations: tuple[Mapping[str, Any], ...] = ()
    blocking: bool = False
    unavailable: bool = False


@dataclass(frozen=True, slots=True)
class ValidationMetrics:
    validators_run: tuple[str, ...]
    nodes_scanned: int
    violations_count: int
    blocking_count: int
    fallback_full_scan: bool


@dataclass(frozen=True, slots=True)
class ValidationReport:
    status: ValidationStatus
    violations: tuple[ConstraintViolation, ...]
    hard_pass: bool
    health_score: float
    metrics: ValidationMetrics


def stable_violation_id(
    *,
    constraint_id: str,
    validator: str,
    affected_node_ids: tuple[str, ...],
    message_code: str,
) -> str:
    payload = {
        "constraint_id": constraint_id,
        "validator": validator,
        "affected_node_ids": sorted(affected_node_ids),
        "message_code": message_code,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    value = 0xCBF29CE484222325
    for byte in raw.encode("utf-8"):
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"cv1-{value:016x}"


def make_violation(
    *,
    constraint: RuntimeConstraint,
    validator: str,
    node_ids: tuple[str, ...],
    message_code: str,
    message: str,
    measured: Any = None,
    expected: Any = None,
    suggested: tuple[Mapping[str, Any], ...] = (),
    unavailable: bool = False,
    policy: ValidationPolicy | None = None,
) -> ConstraintViolation:
    active_policy = policy or ValidationPolicy()
    blocking = constraint.severity == "HARD" and (
        not unavailable or active_policy.unavailable_hard_blocks
    )
    return ConstraintViolation(
        violation_id=stable_violation_id(
            constraint_id=constraint.constraint_id,
            validator=validator,
            affected_node_ids=node_ids,
            message_code=message_code,
        ),
        constraint_id=constraint.constraint_id,
        type=constraint.type,
        validator=validator,
        severity=constraint.severity,
        affected_node_ids=tuple(sorted(node_ids)),
        message=message,
        measured_value=measured,
        expected_value=expected,
        suggested_fix_operations=suggested,
        blocking=blocking,
        unavailable=unavailable,
    )
