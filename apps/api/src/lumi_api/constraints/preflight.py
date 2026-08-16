# ruff: noqa: E501
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from lumi_api.design_ir.document import DesignIRDocument, node_index
from lumi_api.design_ir.engine import apply_batch
from lumi_api.design_ir.nodes import DesignNode, ImageNode
from lumi_api.design_ir.operations import (
    AddNodeOp,
    DesignOperation,
    DesignOperationBatch,
    MoveNodeOp,
    RemoveNodeOp,
    RenameNodeOp,
    ReorderChildrenOp,
    SetAppearanceOp,
    SetFillOp,
    SetImageAssetOp,
    SetImageCropOp,
    SetLockOp,
    SetPageBackgroundOp,
    SetSizeOp,
    SetStrokeOp,
    SetTextOp,
    SetTextStyleOp,
    SetTransformOp,
)

from .models import (
    ConstrainedApplyResult,
    Constraint,
    ConstraintConflict,
    ConstraintOverride,
    ConstraintSet,
    ConstraintViolation,
    PreflightResult,
    SOURCE_PRECEDENCE,
    active_constraints,
    constraint_snapshot_hash,
)
from .registry import EVALUATOR_CONTRACTS


class ConstraintDenied(ValueError):
    def __init__(self, result: PreflightResult) -> None:
        self.result = result
        super().__init__("constraint preflight denied operation batch")


@dataclass(frozen=True)
class AffectedChange:
    target_ids: frozenset[UUID]
    facets: frozenset[str]
    operation_name: str


def _scope_key(constraint: Constraint) -> str:
    payload = constraint.scope.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _parameters_key(constraint: Constraint) -> str:
    return json.dumps(
        constraint.parameters,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def resolve_active_constraints(
    constraint_set: ConstraintSet,
) -> tuple[tuple[Constraint, ...], tuple[ConstraintConflict, ...]]:
    groups: dict[tuple[str, str], list[Constraint]] = defaultdict(list)
    for constraint in active_constraints(constraint_set):
        groups[(constraint.type, _scope_key(constraint))].append(constraint)

    resolved: list[Constraint] = []
    conflicts: list[ConstraintConflict] = []
    severity_rank = {"HARD": 3, "SOFT": 2, "ADVISORY": 1}
    for group in groups.values():
        max_source = max(SOURCE_PRECEDENCE[item.source] for item in group)
        source_winners = [
            item for item in group if SOURCE_PRECEDENCE[item.source] == max_source
        ]
        max_priority = max(item.priority for item in source_winners)
        winners = [item for item in source_winners if item.priority == max_priority]
        if len({_parameters_key(item) for item in winners}) > 1:
            conflicts.append(
                ConstraintConflict(
                    constraint_ids=tuple(sorted((item.id for item in winners), key=str)),
                    type=winners[0].type,
                )
            )
            continue
        strongest = max(severity_rank[item.severity] for item in winners)
        strongest_winners = [
            item for item in winners if severity_rank[item.severity] == strongest
        ]
        resolved.append(min(strongest_winners, key=lambda item: str(item.id)))

    return tuple(sorted(resolved, key=lambda item: str(item.id))), tuple(conflicts)


def _target_matches(
    constraint: Constraint,
    targets: frozenset[UUID],
    nodes: dict[UUID, DesignNode],
) -> bool:
    scope = constraint.scope
    if scope.node_ids and not targets.intersection(scope.node_ids):
        return False
    if scope.semantic_tags:
        target_tags: set[str] = set()
        for target in targets:
            node = nodes.get(target)
            if node is not None:
                target_tags.update(node.semantic_tags)
        if not target_tags.intersection(scope.semantic_tags):
            return False
    return True


def _change_for_operation(
    document: DesignIRDocument,
    operation: DesignOperation,
) -> AffectedChange:
    nodes = node_index(document)
    if isinstance(operation, AddNodeOp):
        if operation.parent_id not in nodes:
            raise KeyError(operation.parent_id)
        return AffectedChange(
            frozenset({operation.parent_id}),
            frozenset({"layer_order", "content"}),
            operation.op,
        )
    if isinstance(operation, RemoveNodeOp):
        if operation.node_id not in nodes:
            raise KeyError(operation.node_id)
        return AffectedChange(
            frozenset({operation.node_id}),
            frozenset({"content", "parent", "layer_order", "identity"}),
            operation.op,
        )
    if isinstance(operation, MoveNodeOp):
        if operation.node_id not in nodes or operation.new_parent_id not in nodes:
            missing = (
                operation.node_id
                if operation.node_id not in nodes
                else operation.new_parent_id
            )
            raise KeyError(missing)
        return AffectedChange(
            frozenset({operation.node_id}),
            frozenset({"parent", "layer_order"}),
            operation.op,
        )
    if isinstance(operation, ReorderChildrenOp):
        if operation.parent_id not in nodes:
            raise KeyError(operation.parent_id)
        return AffectedChange(
            frozenset(operation.child_ids),
            frozenset({"layer_order"}),
            operation.op,
        )
    node = nodes.get(operation.node_id)
    if node is None:
        raise KeyError(operation.node_id)
    if isinstance(operation, SetTransformOp):
        facets = {"transform"}
        if operation.transform.x != node.transform.x or operation.transform.y != node.transform.y:
            facets.add("position")
        if operation.transform.rotation_deg != node.transform.rotation_deg:
            facets.add("rotation")
        if (
            operation.transform.scale_x != node.transform.scale_x
            or operation.transform.scale_y != node.transform.scale_y
        ):
            facets.add("aspect_ratio")
        return AffectedChange(
            frozenset({operation.node_id}), frozenset(facets), operation.op
        )
    if isinstance(operation, SetSizeOp):
        facets = {"size"}
        old_size = getattr(node, "size", None)
        if old_size is not None:
            old_ratio = old_size.width / old_size.height
            new_ratio = operation.size.width / operation.size.height
            if abs(old_ratio - new_ratio) > 1e-9:
                facets.add("aspect_ratio")
        return AffectedChange(
            frozenset({operation.node_id}), frozenset(facets), operation.op
        )
    if isinstance(operation, SetAppearanceOp):
        return AffectedChange(
            frozenset({operation.node_id}), frozenset({"style"}), operation.op
        )
    if isinstance(operation, SetLockOp):
        return AffectedChange(
            frozenset({operation.node_id}), frozenset({"metadata"}), operation.op
        )
    if isinstance(operation, RenameNodeOp):
        return AffectedChange(
            frozenset({operation.node_id}), frozenset({"metadata"}), operation.op
        )
    if isinstance(operation, SetTextOp):
        return AffectedChange(
            frozenset({operation.node_id}),
            frozenset({"text", "content"}),
            operation.op,
        )
    if isinstance(operation, SetTextStyleOp):
        return AffectedChange(
            frozenset({operation.node_id}),
            frozenset({"style", "brand"}),
            operation.op,
        )
    if isinstance(operation, SetImageAssetOp):
        facets = {"asset", "content", "identity"}
        if not isinstance(node, ImageNode):
            facets.add("invalid_target")
        return AffectedChange(
            frozenset({operation.node_id}), frozenset(facets), operation.op
        )
    if isinstance(operation, SetImageCropOp):
        return AffectedChange(
            frozenset({operation.node_id}),
            frozenset({"style", "identity"}),
            operation.op,
        )
    if isinstance(operation, (SetFillOp, SetStrokeOp, SetPageBackgroundOp)):
        return AffectedChange(
            frozenset({operation.node_id}),
            frozenset({"style", "brand"}),
            operation.op,
        )
    raise TypeError(f"unsupported design operation {type(operation)!r}")


def _override_map(
    overrides: Iterable[ConstraintOverride],
) -> dict[UUID, ConstraintOverride]:
    result: dict[UUID, ConstraintOverride] = {}
    for override in overrides:
        if override.constraint_id in result:
            raise ValueError(
                "only one override record per constraint is allowed per evaluation"
            )
        result[override.constraint_id] = override
    return result


def evaluate_preflight(
    document: DesignIRDocument,
    batch: DesignOperationBatch,
    constraint_set: ConstraintSet,
    *,
    overrides: Iterable[ConstraintOverride] = (),
) -> PreflightResult:
    snapshot = constraint_snapshot_hash(constraint_set)
    violations: list[ConstraintViolation] = []
    warnings: list[ConstraintViolation] = []
    applied_overrides: list[UUID] = []
    override_by_constraint = _override_map(overrides)

    if batch.document_id != document.document_id:
        violations.append(
            ConstraintViolation(
                constraint_id=None,
                type=None,
                severity="HARD",
                phase="preflight",
                expected={"document_id": str(document.document_id)},
                actual={"document_id": str(batch.document_id)},
                message_code="CONSTRAINT_DOCUMENT_MISMATCH",
            )
        )
    if batch.base_revision != document.revision:
        violations.append(
            ConstraintViolation(
                constraint_id=None,
                type=None,
                severity="HARD",
                phase="preflight",
                expected={"revision": document.revision},
                actual={"base_revision": batch.base_revision},
                message_code="CONSTRAINT_STALE_DOCUMENT_VERSION",
            )
        )

    resolved, conflicts = resolve_active_constraints(constraint_set)
    for conflict in conflicts:
        violations.append(
            ConstraintViolation(
                constraint_id=conflict.constraint_ids[0],
                type=conflict.type,
                severity="HARD",
                phase="preflight",
                expected={"same_precedence": "single deterministic rule"},
                actual={
                    "conflicting_constraint_ids": [
                        str(item) for item in conflict.constraint_ids
                    ]
                },
                message_code=conflict.message_code,
            )
        )

    nodes = node_index(document)
    for operation in batch.operations:
        try:
            change = _change_for_operation(document, operation)
        except KeyError as error:
            missing = error.args[0]
            violations.append(
                ConstraintViolation(
                    constraint_id=None,
                    type=None,
                    severity="HARD",
                    target_id=missing,
                    phase="preflight",
                    expected={"target_exists": True},
                    actual={"target_exists": False, "operation": operation.op},
                    message_code="CONSTRAINT_TARGET_MISSING",
                )
            )
            continue

        for constraint in resolved:
            contract = EVALUATOR_CONTRACTS[constraint.type]
            if "preflight" not in contract.stages:
                continue
            if not _target_matches(constraint, change.target_ids, nodes):
                continue
            if not set(contract.preflight_facets).intersection(change.facets):
                continue

            override = override_by_constraint.get(constraint.id)
            if override is not None and constraint.source != "SAFETY_SYSTEM":
                applied_overrides.append(override.override_id)
                continue

            violation = ConstraintViolation(
                constraint_id=constraint.id,
                type=constraint.type,
                severity=constraint.severity,
                target_id=next(iter(change.target_ids), None),
                phase="preflight",
                expected={"locked_facets": list(contract.preflight_facets)},
                actual={
                    "operation": change.operation_name,
                    "affected_facets": sorted(change.facets),
                },
                message_code=f"CONSTRAINT_{constraint.type}_VIOLATION",
                repair_hint={"remove_affected_change": True},
                repairable=True,
            )
            if constraint.severity == "HARD":
                violations.append(violation)
            else:
                warnings.append(violation)

    if violations:
        decision = "DENY"
    elif warnings:
        decision = "ALLOW_WITH_WARNINGS"
    else:
        decision = "ALLOW"
    return PreflightResult(
        decision=decision,
        violations=tuple(violations),
        warnings=tuple(warnings),
        conflicts=conflicts,
        constraint_snapshot_hash=snapshot,
        applied_override_ids=tuple(sorted(set(applied_overrides), key=str)),
    )


def apply_batch_with_constraints(
    document: DesignIRDocument,
    batch: DesignOperationBatch,
    constraint_set: ConstraintSet,
    *,
    overrides: Iterable[ConstraintOverride] = (),
) -> ConstrainedApplyResult:
    preflight = evaluate_preflight(
        document,
        batch,
        constraint_set,
        overrides=overrides,
    )
    if preflight.decision == "DENY":
        raise ConstraintDenied(preflight)
    applied = apply_batch(document, batch)
    return ConstrainedApplyResult(
        previous_revision=applied.previous_revision,
        new_revision=applied.new_revision,
        content_hash=applied.content_hash,
        changed_node_ids=applied.changed_node_ids,
        constraint_snapshot_hash=preflight.constraint_snapshot_hash,
    )
