import type { DesignDocument, DesignNode, DesignTransform } from "../../design-ir/src/index";
import type {
  ConstraintViolation,
  DesignConstraint,
  JsonValue,
  ToleranceProfile,
} from "./types";

interface Bounds {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

function number(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function transform(node: DesignNode | undefined): DesignTransform {
  return node?.transform ?? {};
}

function bounds(node: DesignNode | undefined): Bounds {
  const value = transform(node);
  return {
    x: number(value.x),
    y: number(value.y),
    width: Math.max(0, number(value.width)),
    height: Math.max(0, number(value.height)),
  };
}

function close(left: number, right: number, tolerance: number): boolean {
  return Math.abs(left - right) <= tolerance;
}

function jsonComparable(value: unknown): JsonValue {
  if (value === undefined) return null;
  return JSON.parse(JSON.stringify(value)) as JsonValue;
}

function violation(
  constraint: DesignConstraint,
  targetId: string | undefined,
  reasonCode: string,
  expected?: unknown,
  actual?: unknown,
  repairHint?: Readonly<Record<string, JsonValue>>,
): ConstraintViolation {
  const base = {
    constraint_id: constraint.id,
    type: constraint.type,
    severity: constraint.severity,
    validator: "deterministic-ir",
    reason_code: reasonCode,
  } as const;
  return {
    ...base,
    ...(targetId ? { target_id: targetId } : {}),
    ...(expected !== undefined ? { expected: jsonComparable(expected) } : {}),
    ...(actual !== undefined ? { actual: jsonComparable(actual) } : {}),
    ...(repairHint ? { repair_hint: repairHint } : {}),
  };
}

function intersects(left: Bounds, right: Bounds, tolerance: number): boolean {
  const overlapX = Math.min(left.x + left.width, right.x + right.width) - Math.max(left.x, right.x);
  const overlapY = Math.min(left.y + left.height, right.y + right.height) - Math.max(left.y, right.y);
  return overlapX > tolerance && overlapY > tolerance;
}

function inside(inner: Bounds, outer: Bounds, margin: number, tolerance: number): boolean {
  return (
    inner.x + tolerance >= outer.x + margin &&
    inner.y + tolerance >= outer.y + margin &&
    inner.x + inner.width - tolerance <= outer.x + outer.width - margin &&
    inner.y + inner.height - tolerance <= outer.y + outer.height - margin
  );
}

function changedTransform(
  beforeNode: DesignNode,
  afterNode: DesignNode,
  keys: readonly (keyof DesignTransform)[],
  tolerance: number,
): boolean {
  const before = transform(beforeNode);
  const after = transform(afterNode);
  return keys.some((key) => !close(number(before[key]), number(after[key]), tolerance));
}

function compareNodeLock(
  before: DesignDocument,
  after: DesignDocument,
  constraint: DesignConstraint,
  tolerance: ToleranceProfile,
): ConstraintViolation[] {
  const violations: ConstraintViolation[] = [];
  for (const targetId of constraint.scope.node_ids ?? []) {
    const beforeNode = before.nodes[targetId];
    const afterNode = after.nodes[targetId];
    if (!beforeNode || !afterNode) {
      violations.push(
        violation(
          constraint,
          targetId,
          "CONSTRAINT_TARGET_MISSING",
          beforeNode ? "present" : "missing",
          afterNode ? "present" : "missing",
        ),
      );
      continue;
    }
    switch (constraint.type) {
      case "LOCK_POSITION":
        if (changedTransform(beforeNode, afterNode, ["x", "y"], tolerance.position_px))
          violations.push(violation(constraint, targetId, "CONSTRAINT_POSITION_CHANGED", bounds(beforeNode), bounds(afterNode), { action: "restore_position" }));
        break;
      case "LOCK_SIZE":
        if (changedTransform(beforeNode, afterNode, ["width", "height", "scale_x", "scale_y"], tolerance.size_px))
          violations.push(violation(constraint, targetId, "CONSTRAINT_SIZE_CHANGED", bounds(beforeNode), bounds(afterNode), { action: "restore_size" }));
        break;
      case "LOCK_ROTATION":
        if (changedTransform(beforeNode, afterNode, ["rotation_deg"], tolerance.rotation_deg))
          violations.push(violation(constraint, targetId, "CONSTRAINT_ROTATION_CHANGED", transform(beforeNode).rotation_deg ?? 0, transform(afterNode).rotation_deg ?? 0, { action: "restore_rotation" }));
        break;
      case "LOCK_TRANSFORM":
        if (changedTransform(beforeNode, afterNode, ["x", "y", "width", "height", "rotation_deg", "scale_x", "scale_y", "skew_x", "skew_y", "anchor_x", "anchor_y"], Math.max(tolerance.position_px, tolerance.size_px, tolerance.rotation_deg)))
          violations.push(violation(constraint, targetId, "CONSTRAINT_TRANSFORM_CHANGED", transform(beforeNode), transform(afterNode), { action: "restore_transform" }));
        break;
      case "LOCK_ASPECT_RATIO": {
        const beforeBounds = bounds(beforeNode);
        const afterBounds = bounds(afterNode);
        const expected = number(constraint.parameters.ratio, beforeBounds.height ? beforeBounds.width / beforeBounds.height : 0);
        const actual = afterBounds.height ? afterBounds.width / afterBounds.height : 0;
        if (!close(expected, actual, tolerance.aspect_ratio))
          violations.push(violation(constraint, targetId, "CONSTRAINT_ASPECT_RATIO_CHANGED", expected, actual, { action: "restore_aspect_ratio" }));
        break;
      }
      case "LOCK_LAYER_ORDER": {
        const parentId = beforeNode.parent_id;
        const beforeIndex = parentId ? before.nodes[parentId]?.children.indexOf(targetId) ?? -1 : -1;
        const afterIndex = parentId ? after.nodes[parentId]?.children.indexOf(targetId) ?? -1 : -1;
        if (beforeIndex !== afterIndex)
          violations.push(violation(constraint, targetId, "CONSTRAINT_LAYER_ORDER_CHANGED", beforeIndex, afterIndex, { action: "restore_layer_order" }));
        break;
      }
      case "LOCK_PARENT":
        if (beforeNode.parent_id !== afterNode.parent_id)
          violations.push(violation(constraint, targetId, "CONSTRAINT_PARENT_CHANGED", beforeNode.parent_id, afterNode.parent_id, { action: "restore_parent" }));
        break;
      case "LOCK_TEXT":
        if (beforeNode.content !== afterNode.content)
          violations.push(violation(constraint, targetId, "CONSTRAINT_TEXT_CHANGED", beforeNode.content, afterNode.content, { action: "restore_text" }));
        break;
      case "LOCK_ASSET":
        if (beforeNode.asset_id !== afterNode.asset_id)
          violations.push(violation(constraint, targetId, "CONSTRAINT_ASSET_CHANGED", beforeNode.asset_id, afterNode.asset_id, { action: "restore_asset" }));
        break;
      case "LOCK_STYLE":
        if (JSON.stringify(beforeNode.style_refs ?? []) !== JSON.stringify(afterNode.style_refs ?? []))
          violations.push(violation(constraint, targetId, "CONSTRAINT_STYLE_CHANGED", beforeNode.style_refs ?? [], afterNode.style_refs ?? [], { action: "restore_style" }));
        break;
      case "LOCK_BRAND":
        if (JSON.stringify(beforeNode.brand_binding ?? null) !== JSON.stringify(afterNode.brand_binding ?? null))
          violations.push(violation(constraint, targetId, "CONSTRAINT_BRAND_BINDING_CHANGED", beforeNode.brand_binding ?? null, afterNode.brand_binding ?? null, { action: "restore_brand_binding" }));
        break;
      case "LOCK_CONTENT": {
        const keys = ["content", "asset_id", "source_artifact_version_id", "semantic"] as const;
        const expected = Object.fromEntries(keys.map((key) => [key, beforeNode[key]]));
        const actual = Object.fromEntries(keys.map((key) => [key, afterNode[key]]));
        if (JSON.stringify(expected) !== JSON.stringify(actual))
          violations.push(violation(constraint, targetId, "CONSTRAINT_CONTENT_CHANGED", expected, actual, { action: "restore_content" }));
        break;
      }
      default:
        break;
    }
  }
  return violations;
}

function compareRegionRule(
  after: DesignDocument,
  constraint: DesignConstraint,
  tolerance: ToleranceProfile,
): ConstraintViolation[] {
  const violations: ConstraintViolation[] = [];
  const targets = constraint.scope.node_ids ?? [];
  if (constraint.type === "MUST_NOT_OVERLAP") {
    const forbidden = Array.isArray(constraint.parameters.forbidden_node_ids)
      ? constraint.parameters.forbidden_node_ids.filter((value): value is string => typeof value === "string")
      : [];
    for (const targetId of targets) {
      const target = after.nodes[targetId];
      if (!target) continue;
      for (const forbiddenId of forbidden) {
        const other = after.nodes[forbiddenId];
        if (other && intersects(bounds(target), bounds(other), tolerance.overlap_px))
          violations.push(violation(constraint, targetId, "CONSTRAINT_OVERLAP", forbiddenId, { target: bounds(target), forbidden: bounds(other) }, { action: "move_outside_overlap", forbidden_node_id: forbiddenId }));
      }
    }
    return violations;
  }

  const containerId = typeof constraint.parameters.container_id === "string" ? constraint.parameters.container_id : constraint.scope.frame_id;
  const container = containerId ? after.nodes[containerId] : undefined;
  const safe = constraint.scope.region;
  for (const targetId of targets) {
    const target = after.nodes[targetId];
    if (!target) continue;
    if (constraint.type === "SAFE_AREA" && safe) {
      const outer = { x: safe.x, y: safe.y, width: safe.width, height: safe.height };
      if (!inside(bounds(target), outer, 0, tolerance.position_px))
        violations.push(violation(constraint, targetId, "CONSTRAINT_OUTSIDE_SAFE_AREA", outer, bounds(target), { action: "move_inside_safe_area" }));
      continue;
    }
    if (!container) continue;
    if (constraint.type === "MUST_STAY_INSIDE") {
      if (!inside(bounds(target), bounds(container), 0, tolerance.position_px))
        violations.push(violation(constraint, targetId, "CONSTRAINT_OUTSIDE_CONTAINER", bounds(container), bounds(target), { action: "move_inside", container_id: container.id }));
    }
    if (constraint.type === "MIN_MARGIN") {
      const margin = number(constraint.parameters.min_px, 0);
      if (!inside(bounds(target), bounds(container), margin, tolerance.position_px))
        violations.push(violation(constraint, targetId, "CONSTRAINT_MARGIN_TOO_SMALL", margin, { target: bounds(target), container: bounds(container) }, { action: "increase_margin", min_px: margin }));
    }
  }
  return violations;
}

export function evaluateDeterministicConstraint(
  before: DesignDocument,
  after: DesignDocument,
  constraint: DesignConstraint,
  tolerance: ToleranceProfile,
): readonly ConstraintViolation[] {
  const nodeRules = new Set([
    "LOCK_POSITION",
    "LOCK_SIZE",
    "LOCK_ROTATION",
    "LOCK_TRANSFORM",
    "LOCK_ASPECT_RATIO",
    "LOCK_LAYER_ORDER",
    "LOCK_PARENT",
    "LOCK_CONTENT",
    "LOCK_TEXT",
    "LOCK_ASSET",
    "LOCK_STYLE",
    "LOCK_BRAND",
  ]);
  if (nodeRules.has(constraint.type)) return compareNodeLock(before, after, constraint, tolerance);
  if (["MUST_STAY_INSIDE", "MUST_NOT_OVERLAP", "MIN_MARGIN", "SAFE_AREA"].includes(constraint.type))
    return compareRegionRule(after, constraint, tolerance);
  return [];
}
