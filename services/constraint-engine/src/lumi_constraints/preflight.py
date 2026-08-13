from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from lumi_design_ir import DesignIRError, apply_operation

from .model import Constraint, OverrideAudit, PreflightResult, Violation
from .precedence import detect_conflicts, effective_constraints
from .registry import EVALUATORS


BROAD_CHANGE_SET = frozenset(
    {
        "existence",
        "position",
        "size",
        "rotation",
        "transform",
        "parent",
        "layer_order",
        "content",
        "text",
        "asset",
        "style",
        "brand",
    }
)

MESSAGE_CODES = {
    "position": "CONSTRAINT_POSITION_CHANGED",
    "size": "CONSTRAINT_SIZE_CHANGED",
    "rotation": "CONSTRAINT_ROTATION_CHANGED",
    "transform": "CONSTRAINT_TRANSFORM_CHANGED",
    "parent": "CONSTRAINT_PARENT_CHANGED",
    "layer_order": "CONSTRAINT_LAYER_ORDER_CHANGED",
    "content": "CONSTRAINT_CONTENT_CHANGED",
    "text": "CONSTRAINT_TEXT_CHANGED",
    "asset": "CONSTRAINT_ASSET_CHANGED",
    "style": "CONSTRAINT_STYLE_CHANGED",
    "brand": "CONSTRAINT_BRAND_CHANGED",
    "existence": "CONSTRAINT_CONTENT_CHANGED",
}


def _nodes(document: Mapping[str, Any]) -> Mapping[str, Any]:
    nodes = document.get("nodes")
    if not isinstance(nodes, Mapping):
        return {}
    return nodes


def _node(document: Mapping[str, Any], node_id: str) -> Mapping[str, Any] | None:
    value = _nodes(document).get(node_id)
    return value if isinstance(value, Mapping) else None


def _transform(node: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if node is None:
        return {}
    value = node.get("transform")
    return value if isinstance(value, Mapping) else {}


def _index_in_parent(document: Mapping[str, Any], node_id: str) -> int | None:
    node = _node(document, node_id)
    if node is None:
        return None
    parent_id = node.get("parent_id")
    if not isinstance(parent_id, str):
        return None
    parent = _node(document, parent_id)
    if parent is None:
        return None
    children = parent.get("children")
    if not isinstance(children, list) or node_id not in children:
        return None
    return children.index(node_id)


def _changed_properties(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, frozenset[str]]:
    changes: dict[str, frozenset[str]] = {}
    before_nodes = _nodes(before)
    after_nodes = _nodes(after)
    for node_id in sorted(set(before_nodes) | set(after_nodes)):
        old = _node(before, node_id)
        new = _node(after, node_id)
        if old is None or new is None:
            changes[node_id] = BROAD_CHANGE_SET
            continue

        changed: set[str] = set()
        old_transform = _transform(old)
        new_transform = _transform(new)
        if any(old_transform.get(key) != new_transform.get(key) for key in ("x", "y")):
            changed.update({"position", "transform"})
        if any(old_transform.get(key) != new_transform.get(key) for key in ("width", "height")):
            changed.update({"size", "transform"})
        if old_transform.get("rotation_deg") != new_transform.get("rotation_deg"):
            changed.update({"rotation", "transform"})
        if any(
            old_transform.get(key) != new_transform.get(key)
            for key in ("scale_x", "scale_y", "skew_x", "skew_y", "anchor_x", "anchor_y")
        ):
            changed.add("transform")

        if old.get("parent_id") != new.get("parent_id"):
            changed.add("parent")
        if _index_in_parent(before, node_id) != _index_in_parent(after, node_id):
            changed.add("layer_order")

        old_text = old.get("text") if isinstance(old.get("text"), Mapping) else None
        new_text = new.get("text") if isinstance(new.get("text"), Mapping) else None
        if old_text is not None or new_text is not None:
            if (old_text or {}).get("content") != (new_text or {}).get("content") or (
                old_text or {}
            ).get("spans") != (new_text or {}).get("spans"):
                changed.update({"text", "content"})
            old_style_text = dict(old_text or {})
            new_style_text = dict(new_text or {})
            old_style_text.pop("content", None)
            old_style_text.pop("spans", None)
            new_style_text.pop("content", None)
            new_style_text.pop("spans", None)
            if old_style_text != new_style_text:
                changed.add("style")

        def asset_id(node: Mapping[str, Any]) -> Any:
            for field in ("image", "video"):
                payload = node.get(field)
                if isinstance(payload, Mapping) and "asset_id" in payload:
                    return payload.get("asset_id")
            return None

        if asset_id(old) != asset_id(new):
            changed.update({"asset", "content"})

        if old.get("style_refs") != new.get("style_refs"):
            changed.add("style")
        if any(old.get(key) != new.get(key) for key in ("opacity", "blend_mode")):
            changed.add("style")
        if old.get("shape") != new.get("shape") or old.get("vector_path") != new.get("vector_path"):
            changed.update({"style", "content"})
        if old.get("frame") != new.get("frame"):
            changed.update({"style", "brand"})

        if changed:
            changes[node_id] = frozenset(changed)
    return changes


def _targets(
    document: Mapping[str, Any],
    constraint: Constraint,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    nodes = _nodes(document)
    targets: set[str] = set()
    missing: set[str] = set()
    for node_id in (*constraint.scope.node_ids, *constraint.scope.frame_ids):
        if node_id in nodes:
            targets.add(node_id)
        else:
            missing.add(node_id)
    if constraint.scope.roles:
        role_set = set(constraint.scope.roles)
        for node_id, raw_node in nodes.items():
            if isinstance(raw_node, Mapping) and raw_node.get("role") in role_set:
                targets.add(str(node_id))
    return tuple(sorted(targets)), tuple(sorted(missing))


def _rect(document: Mapping[str, Any], node_id: str) -> tuple[float, float, float, float] | None:
    node = _node(document, node_id)
    transform = _transform(node)
    try:
        return (
            float(transform["x"]),
            float(transform["y"]),
            float(transform["width"]),
            float(transform["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _contains(container: tuple[float, float, float, float], item: tuple[float, float, float, float]) -> bool:
    cx, cy, cw, ch = container
    x, y, w, h = item
    return x >= cx and y >= cy and x + w <= cx + cw and y + h <= cy + ch


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def _constraint_region(
    document: Mapping[str, Any], constraint: Constraint, target_id: str
) -> tuple[float, float, float, float] | None:
    region = constraint.scope.region
    if region is not None:
        try:
            rx = float(region["x"])
            ry = float(region["y"])
            rw = float(region["width"])
            rh = float(region["height"])
        except (KeyError, TypeError, ValueError):
            return None
        if region.get("normalized") is True:
            node = _node(document, target_id)
            parent_id = node.get("parent_id") if node is not None else None
            if not isinstance(parent_id, str):
                return None
            parent = _rect(document, parent_id)
            if parent is None:
                return None
            px, py, pw, ph = parent
            return px + rx * pw, py + ry * ph, rw * pw, rh * ph
        return rx, ry, rw, rh

    container_id = constraint.parameters.get("container_node_id")
    if isinstance(container_id, str):
        return _rect(document, container_id)
    node = _node(document, target_id)
    parent_id = node.get("parent_id") if node is not None else None
    if isinstance(parent_id, str):
        return _rect(document, parent_id)
    return None


def _override_active(constraint: Constraint, overrides: Mapping[str, OverrideAudit]) -> bool:
    audit = overrides.get(constraint.id)
    if audit is None:
        return False
    return (
        audit.authorized is True
        and audit.constraint_id == constraint.id
        and constraint.source != "SAFETY_SYSTEM"
        and constraint.override_policy == "AUTHORIZED"
    )


def _violation(
    constraint: Constraint,
    *,
    target_id: str | None,
    message_code: str,
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    repair_hint: Mapping[str, Any] | None = None,
) -> Violation:
    return Violation(
        constraint_id=constraint.id,
        type=constraint.type,
        severity=constraint.severity,
        phase="PREFLIGHT",
        target_id=target_id,
        expected=expected,
        actual=actual,
        message_code=message_code,
        repair_hint=repair_hint or {},
        overrideable=constraint.source != "SAFETY_SYSTEM" and constraint.override_policy == "AUTHORIZED",
    )


def _missing_target_violations(
    constraint: Constraint, missing: tuple[str, ...]
) -> list[Violation]:
    return [
        _violation(
            constraint,
            target_id=node_id,
            message_code="CONSTRAINT_TARGET_MISSING",
            expected={"target_exists": True},
            actual={"target_exists": False},
            repair_hint={"action": "refresh_constraint_scope"},
        )
        for node_id in missing
    ]


def _evaluate_constraint(
    before: Mapping[str, Any],
    candidate: Mapping[str, Any],
    changes: Mapping[str, frozenset[str]],
    constraint: Constraint,
) -> list[Violation]:
    spec = EVALUATORS.get(constraint.type)
    if spec is None or spec.phase not in {"PREFLIGHT", "BOTH"}:
        return []

    targets, missing = _targets(before, constraint)
    violations = _missing_target_violations(constraint, missing)

    if spec.evaluator in {"lock_property", "lock_content"}:
        for target_id in targets:
            changed = changes.get(target_id, frozenset())
            forbidden = changed.intersection(spec.properties)
            if forbidden:
                first = sorted(forbidden)[0]
                violations.append(
                    _violation(
                        constraint,
                        target_id=target_id,
                        message_code=MESSAGE_CODES.get(first, "CONSTRAINT_LOCKED_PROPERTY_CHANGED"),
                        expected={"unchanged": sorted(spec.properties)},
                        actual={"changed": sorted(changed)},
                        repair_hint={"action": "remove_change_to_locked_property"},
                    )
                )
        return violations

    if spec.evaluator == "aspect_ratio":
        tolerance = float(constraint.parameters.get("tolerance", 1e-6))
        for target_id in targets:
            if "size" not in changes.get(target_id, frozenset()):
                continue
            old_rect = _rect(before, target_id)
            new_rect = _rect(candidate, target_id)
            if old_rect is None or new_rect is None:
                continue
            _, _, old_w, old_h = old_rect
            _, _, new_w, new_h = new_rect
            if old_h == 0 or new_h == 0:
                same = old_w == new_w and old_h == new_h
                old_ratio = new_ratio = None
            else:
                old_ratio = old_w / old_h
                new_ratio = new_w / new_h
                same = abs(old_ratio - new_ratio) <= tolerance
            if not same:
                violations.append(
                    _violation(
                        constraint,
                        target_id=target_id,
                        message_code="CONSTRAINT_ASPECT_RATIO_CHANGED",
                        expected={"ratio": old_ratio, "tolerance": tolerance},
                        actual={"ratio": new_ratio},
                        repair_hint={"action": "resize_proportionally"},
                    )
                )
        return violations

    if spec.evaluator == "protected_region":
        protected_region = constraint.scope.region
        if protected_region is not None and not targets:
            for changed_id in changes:
                changed_rect = _rect(candidate, changed_id)
                region_rect = _constraint_region(candidate, constraint, changed_id)
                if changed_rect is not None and region_rect is not None and _overlaps(changed_rect, region_rect):
                    violations.append(
                        _violation(
                            constraint,
                            target_id=changed_id,
                            message_code="CONSTRAINT_PROTECTED_REGION_CHANGED",
                            expected={"protected_region": dict(protected_region)},
                            actual={"changed_properties": sorted(changes[changed_id])},
                            repair_hint={"action": "exclude_protected_region"},
                        )
                    )
            return violations
        for target_id in targets:
            forbidden = changes.get(target_id, frozenset()).intersection(spec.properties)
            if forbidden:
                violations.append(
                    _violation(
                        constraint,
                        target_id=target_id,
                        message_code="CONSTRAINT_PROTECTED_REGION_CHANGED",
                        expected={"unchanged": True},
                        actual={"changed": sorted(forbidden)},
                        repair_hint={"action": "restore_protected_content"},
                    )
                )
        return violations

    if spec.evaluator in {"inside_region", "min_margin"}:
        margin = float(constraint.parameters.get("margin", 0)) if spec.evaluator == "min_margin" else 0.0
        for target_id in targets:
            if not changes.get(target_id, frozenset()).intersection(spec.properties):
                continue
            item = _rect(candidate, target_id)
            container = _constraint_region(candidate, constraint, target_id)
            if item is None or container is None:
                continue
            cx, cy, cw, ch = container
            allowed = (cx + margin, cy + margin, max(0.0, cw - 2 * margin), max(0.0, ch - 2 * margin))
            if not _contains(allowed, item):
                violations.append(
                    _violation(
                        constraint,
                        target_id=target_id,
                        message_code=(
                            "CONSTRAINT_MIN_MARGIN_VIOLATED"
                            if spec.evaluator == "min_margin"
                            else "CONSTRAINT_OUTSIDE_ALLOWED_REGION"
                        ),
                        expected={"allowed_rect": allowed, "margin": margin},
                        actual={"node_rect": item},
                        repair_hint={"action": "move_or_resize_inside_allowed_region"},
                    )
                )
        return violations

    if spec.evaluator == "non_overlap":
        other_ids = constraint.parameters.get("other_node_ids", ())
        if not isinstance(other_ids, (tuple, list)):
            other_ids = ()
        for target_id in targets:
            if not changes.get(target_id, frozenset()).intersection(spec.properties):
                continue
            item = _rect(candidate, target_id)
            if item is None:
                continue
            for other_id in other_ids:
                if not isinstance(other_id, str) or other_id == target_id:
                    continue
                other = _rect(candidate, other_id)
                if other is not None and _overlaps(item, other):
                    violations.append(
                        _violation(
                            constraint,
                            target_id=target_id,
                            message_code="CONSTRAINT_OVERLAP_DETECTED",
                            expected={"must_not_overlap": other_id},
                            actual={"node_rect": item, "other_rect": other},
                            repair_hint={"action": "separate_nodes"},
                        )
                    )
        return violations

    return violations


def preflight(
    document: dict[str, Any],
    operation: dict[str, Any],
    constraints: Iterable[Constraint],
    *,
    current_document_version: int,
    overrides: Mapping[str, OverrideAudit] | None = None,
) -> PreflightResult:
    override_map = overrides or {}
    all_constraints = tuple(constraints)
    conflicts = detect_conflicts(all_constraints)
    hard_conflicts = tuple(item for item in conflicts if item.severity == "HARD")
    if hard_conflicts:
        return PreflightResult("DENY", None, None, hard_conflicts, tuple(item for item in conflicts if item.severity != "HARD"))

    try:
        applied = apply_operation(document, operation, current_version=current_document_version)
    except DesignIRError as exc:
        violation = Violation(
            constraint_id="__operation__",
            type="DESIGN_IR_OPERATION",
            severity="HARD",
            phase="PREFLIGHT",
            target_id=None,
            expected={"valid_operation": True, "document_version": current_document_version},
            actual={"error": type(exc).__name__, "detail": str(exc)},
            message_code="CONSTRAINT_OPERATION_INVALID",
            repair_hint={"action": "repair_design_operation"},
            overrideable=False,
        )
        return PreflightResult("DENY", None, None, (violation,), ())

    changes = _changed_properties(document, applied.document)
    hard: list[Violation] = []
    warnings: list[Violation] = [item for item in conflicts if item.severity != "HARD"]

    for constraint in effective_constraints(all_constraints):
        if _override_active(constraint, override_map):
            continue
        for violation in _evaluate_constraint(document, applied.document, changes, constraint):
            if violation.severity == "HARD":
                hard.append(violation)
            else:
                warnings.append(violation)

    if hard:
        decision = "DENY"
    elif warnings:
        decision = "ALLOW_WITH_WARNINGS"
    else:
        decision = "ALLOW"
    return PreflightResult(
        decision,
        applied.document,
        applied.document_version,
        tuple(hard),
        tuple(warnings),
    )
