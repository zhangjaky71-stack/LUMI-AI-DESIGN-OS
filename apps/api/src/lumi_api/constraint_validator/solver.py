from __future__ import annotations

from typing import Any, Mapping

from .contracts import ConstraintViolation, RuntimeConstraint, ValidationAdapters, ValidationPolicy
from .runtime import validate_constraints

_FORBIDDEN_AUTOFIX_VALIDATORS = {
    "ProtectedRegionValidator",
    "BrandTokenValidator",
    "IdentityPreservationValidator",
}


def propose_fix_operations(
    violations: tuple[ConstraintViolation, ...],
    *,
    document_version: int,
) -> tuple[Mapping[str, Any], ...]:
    values: list[Mapping[str, Any]] = []
    for item in violations:
        if item.validator in _FORBIDDEN_AUTOFIX_VALIDATORS or not item.affected_node_ids:
            continue
        node_id = item.affected_node_ids[0]
        suffix = item.violation_id[:12]
        if item.validator in {"BoundsValidator", "SafeAreaValidator"} and isinstance(
            item.expected_value, (tuple, list)
        ):
            x, y, _, _ = item.expected_value
            values.append(
                {
                    "operation_id": f"autofix:{suffix}:move",
                    "type": "MOVE_NODE",
                    "target_ids": [node_id],
                    "expected_document_version": document_version,
                    "payload": {"x": x, "y": y},
                    "reason": "constraint-validator-safe-autofix",
                }
            )
        elif item.validator == "FontSizeValidator" and isinstance(
            item.expected_value, (int, float)
        ):
            values.append(
                {
                    "operation_id": f"autofix:{suffix}:font",
                    "type": "SET_PROPERTY",
                    "target_ids": [node_id],
                    "expected_document_version": document_version,
                    "payload": {"property": "font_size", "value": item.expected_value},
                    "reason": "constraint-validator-safe-autofix",
                }
            )
        elif item.validator == "AspectRatioValidator" and isinstance(
            item.expected_value, (int, float)
        ):
            values.append(
                {
                    "operation_id": f"autofix:{suffix}:ratio",
                    "type": "RESIZE_NODE",
                    "target_ids": [node_id],
                    "expected_document_version": document_version,
                    "payload": {"width": float(item.expected_value) * 100.0, "height": 100.0},
                    "reason": "constraint-validator-safe-autofix",
                }
            )
    return tuple(values)


def validate_proposed_fix(
    document: Mapping[str, Any],
    constraints: tuple[RuntimeConstraint, ...],
    operation: Mapping[str, Any],
    *,
    adapters: ValidationAdapters | None = None,
    policy: ValidationPolicy | None = None,
):
    return validate_constraints(
        document,
        constraints,
        operation=operation,
        adapters=adapters,
        policy=policy,
    )


def validate_proposed_fix_with_ir_runtime(
    document: Mapping[str, Any],
    constraints: tuple[RuntimeConstraint, ...],
    operation: Mapping[str, Any],
    *,
    apply_ir_runtime,
    adapters: ValidationAdapters | None = None,
    policy: ValidationPolicy | None = None,
):
    """Apply through NODE-38 (or its adapter), then run a second constraint validation."""
    candidate = apply_ir_runtime(document, operation)
    return validate_constraints(
        candidate,
        constraints,
        adapters=adapters,
        policy=policy,
        force_full=True,
    )
