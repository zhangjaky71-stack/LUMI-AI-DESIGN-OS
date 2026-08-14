import { executeOperations } from "../../design-ir/src/index";
import { aggregateViolations, preflightDecision } from "./aggregator";
import { evaluateDeterministicConstraint } from "./evaluators";
import { isConstraintOverridden } from "./override";
import { resolveConstraints } from "./resolver";
import type {
  ConstraintOverrideToken,
  ConstraintViolation,
  DesignConstraint,
  DesignDocument,
  DesignOperation,
  GuardedExecutionResult,
  PreflightReport,
  ToleranceProfile,
} from "./types";
import { DEFAULT_TOLERANCE } from "./types";

function conflictViolations(
  constraints: readonly DesignConstraint[],
  conflicts: ReturnType<typeof resolveConstraints>["conflicts"],
): ConstraintViolation[] {
  const byId = new Map(constraints.map((constraint) => [constraint.id, constraint]));
  return conflicts.map((conflict) => {
    const first = byId.get(conflict.constraint_ids[0]!)!;
    return {
      constraint_id: conflict.constraint_ids.join(","),
      type: first.type,
      severity: "HARD",
      validator: "constraint-resolver",
      reason_code: "CONSTRAINT_CONFLICT",
      ...(conflict.target_ids[0] ? { target_id: conflict.target_ids[0] } : {}),
      expected: [...conflict.constraint_ids],
      repair_hint: { action: "resolve_constraint_conflict" },
    };
  });
}

function staleViolations(
  constraints: readonly DesignConstraint[],
  staleIds: readonly string[],
): ConstraintViolation[] {
  const byId = new Map(constraints.map((constraint) => [constraint.id, constraint]));
  return staleIds.map((id) => {
    const constraint = byId.get(id)!;
    return {
      constraint_id: id,
      type: constraint.type,
      severity: constraint.severity === "HARD" ? "HARD" : "SOFT",
      validator: "constraint-resolver",
      reason_code: "STALE_CONSTRAINT_SNAPSHOT",
      expected: constraint.document_version ?? null,
      repair_hint: { action: "refresh_constraint_snapshot" },
    };
  });
}

export function preflightOperations(
  document: DesignDocument,
  operations: readonly DesignOperation[],
  constraints: readonly DesignConstraint[],
  options: {
    readonly overrides?: readonly ConstraintOverrideToken[];
    readonly tolerance?: ToleranceProfile;
  } = {},
): GuardedExecutionResult {
  const resolved = resolveConstraints(document, constraints);
  const initialViolations = [
    ...conflictViolations(constraints, resolved.conflicts),
    ...staleViolations(constraints, resolved.stale_constraint_ids),
  ];
  if (initialViolations.some((item) => item.severity === "HARD")) {
    const aggregated = aggregateViolations(initialViolations);
    return {
      preflight: {
        decision: preflightDecision(aggregated),
        violations: aggregated,
        conflicts: resolved.conflicts,
        effective_constraint_ids: resolved.constraints.map((item) => item.id),
      },
    };
  }

  const execution = executeOperations(document, operations);
  if (!execution.ok) {
    return {
      preflight: {
        decision: "DENY",
        violations: initialViolations,
        conflicts: resolved.conflicts,
        effective_constraint_ids: resolved.constraints.map((item) => item.id),
      },
      execution,
    };
  }

  const tolerance = options.tolerance ?? DEFAULT_TOLERANCE;
  const violations: ConstraintViolation[] = [...initialViolations];
  for (const constraint of resolved.constraints) {
    if (isConstraintOverridden(document, constraint, options.overrides)) continue;
    violations.push(
      ...evaluateDeterministicConstraint(document, execution.document, constraint, tolerance),
    );
  }
  const aggregated = aggregateViolations(violations);
  const report: PreflightReport = {
    decision: preflightDecision(aggregated),
    violations: aggregated,
    conflicts: resolved.conflicts,
    effective_constraint_ids: resolved.constraints.map((item) => item.id),
  };
  return report.decision === "DENY" ? { preflight: report } : { preflight: report, execution };
}

/**
 * Server-side enforcement boundary: callers persist the returned candidate only when an execution
 * object exists and preflight is not DENY. The constraint package never mutates persisted IR itself.
 */
export function guardedExecute(
  document: DesignDocument,
  operations: readonly DesignOperation[],
  constraints: readonly DesignConstraint[],
  options: {
    readonly overrides?: readonly ConstraintOverrideToken[];
    readonly tolerance?: ToleranceProfile;
  } = {},
): GuardedExecutionResult {
  return preflightOperations(document, operations, constraints, options);
}
