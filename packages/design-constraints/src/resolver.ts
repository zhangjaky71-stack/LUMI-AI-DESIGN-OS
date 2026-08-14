import { canonicalStringify } from "../../design-ir/src/index";
import type {
  ConstraintConflict,
  ConstraintSource,
  DesignConstraint,
  DesignDocument,
} from "./types";

export const SOURCE_PRECEDENCE: Readonly<Record<ConstraintSource, number>> = Object.freeze({
  SAFETY_SYSTEM: 700,
  USER_EXPLICIT: 600,
  APPROVED_BRAND_RULE: 500,
  PROJECT_RULE: 400,
  RECIPE_RULE: 300,
  AGENT_INFERRED: 200,
  STYLE_PREFERENCE: 100,
});

function scopeKey(constraint: DesignConstraint): string {
  return canonicalStringify({
    type: constraint.type,
    node_ids: [...(constraint.scope.node_ids ?? [])].sort(),
    frame_id: constraint.scope.frame_id ?? null,
    region: constraint.scope.region ?? null,
  });
}

function parameterKey(constraint: DesignConstraint): string {
  return canonicalStringify(constraint.parameters);
}

export interface ResolvedConstraintSet {
  readonly constraints: readonly DesignConstraint[];
  readonly conflicts: readonly ConstraintConflict[];
  readonly stale_constraint_ids: readonly string[];
}

/**
 * Resolves active constraints deterministically. A stale snapshot is excluded from enforcement and
 * surfaced explicitly. Equal-precedence incompatible rules become conflicts rather than silently
 * picking a winner.
 */
export function resolveConstraints(
  document: DesignDocument,
  constraints: readonly DesignConstraint[],
): ResolvedConstraintSet {
  const currentVersion =
    typeof document.metadata.document_version === "number" ? document.metadata.document_version : 0;
  const active = constraints.filter((constraint) => constraint.active);
  const stale = active
    .filter(
      (constraint) =>
        constraint.document_version !== undefined && constraint.document_version !== currentVersion,
    )
    .map((constraint) => constraint.id)
    .sort();
  const current = active.filter((constraint) => !stale.includes(constraint.id));

  const groups = new Map<string, DesignConstraint[]>();
  for (const constraint of current) {
    const key = scopeKey(constraint);
    const bucket = groups.get(key) ?? [];
    bucket.push(constraint);
    groups.set(key, bucket);
  }

  const effective: DesignConstraint[] = [];
  const conflicts: ConstraintConflict[] = [];
  for (const bucket of groups.values()) {
    bucket.sort((left, right) => {
      const source = SOURCE_PRECEDENCE[right.source] - SOURCE_PRECEDENCE[left.source];
      if (source) return source;
      const priority = right.priority - left.priority;
      if (priority) return priority;
      return left.id.localeCompare(right.id);
    });
    const winner = bucket[0]!;
    const peers = bucket.filter(
      (candidate) =>
        SOURCE_PRECEDENCE[candidate.source] === SOURCE_PRECEDENCE[winner.source] &&
        candidate.priority === winner.priority,
    );
    const parameterShapes = new Set(peers.map(parameterKey));
    if (peers.length > 1 && parameterShapes.size > 1) {
      conflicts.push({
        constraint_ids: peers.map((item) => item.id).sort(),
        reason_code: "CONSTRAINT_CONFLICT",
        target_ids: [...(winner.scope.node_ids ?? [])].sort(),
      });
      continue;
    }
    effective.push(winner);
  }

  effective.sort((left, right) => left.id.localeCompare(right.id));
  conflicts.sort((left, right) => left.constraint_ids.join(":").localeCompare(right.constraint_ids.join(":")));
  return { constraints: effective, conflicts, stale_constraint_ids: stale };
}
