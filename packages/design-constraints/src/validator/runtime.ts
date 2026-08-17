import { impactSet } from "./impact";
import { projectOperation } from "./projection";
import type {
  ConstraintViolation,
  DesignDocumentLike,
  DesignOperationLike,
  IrIssueLike,
  RuntimeConstraint,
  ValidationAdapters,
  ValidationPhase,
  ValidationPolicy,
  ValidationReport,
} from "./types";
import { VALIDATOR_SPECS } from "./validators";

const DEFAULT_POLICY: ValidationPolicy = {
  incremental_full_scan_ratio: 0.4,
  incremental_full_scan_node_limit: 500,
  unavailable_hard_blocks: true,
  max_auto_fix_rounds: 1,
};

const LOCKED_OPERATION_TYPES: Readonly<Record<string, readonly string[]>> = {
  LOCK_POSITION: ["MOVE_NODE"],
  LOCK_SIZE: ["RESIZE_NODE"],
  LOCK_ROTATION: ["ROTATE_NODE"],
  LOCK_TRANSFORM: ["MOVE_NODE", "RESIZE_NODE", "ROTATE_NODE"],
  LOCK_LAYER_ORDER: ["REORDER_NODE"],
  LOCK_PARENT: ["REPARENT_NODE"],
  LOCK_CONTENT: ["SET_TEXT", "REPLACE_ASSET", "DELETE_NODE"],
  LOCK_TEXT: ["SET_TEXT"],
  LOCK_ASSET: ["REPLACE_ASSET"],
  LOCK_STYLE: ["APPLY_STYLE", "SET_PROPERTY"],
};

function lockApplies(
  constraint: RuntimeConstraint,
  operation: DesignOperationLike | undefined,
): boolean {
  if (!operation) return false;
  return LOCKED_OPERATION_TYPES[constraint.type]?.includes(operation.type) ?? false;
}

function healthScore(
  constraints: readonly RuntimeConstraint[],
  violations: readonly ConstraintViolation[],
): number {
  const weights = { HARD: 5, SOFT: 2, ADVISORY: 1 } as const;
  const active = constraints.filter((item) => item.active !== false);
  const denominator = active.reduce((sum, item) => sum + weights[item.severity], 0);
  if (!denominator) return 100;
  const failed = new Set(violations.map((item) => item.constraint_id));
  const penalty = active.reduce(
    (sum, item) => sum + (failed.has(item.constraint_id) ? weights[item.severity] : 0),
    0,
  );
  return Math.round(Math.max(0, 100 * (1 - penalty / denominator)) * 10_000) / 10_000;
}

function sortViolations(values: readonly ConstraintViolation[]): readonly ConstraintViolation[] {
  const dedup = new Map(values.map((item) => [item.violation_id, item]));
  return [...dedup.values()].sort((a, b) => {
    const left = `${a.constraint_id}\u0000${a.validator}\u0000${a.affected_node_ids.join(",")}\u0000${a.violation_id}`;
    const right = `${b.constraint_id}\u0000${b.validator}\u0000${b.affected_node_ids.join(",")}\u0000${b.violation_id}`;
    return left < right ? -1 : left > right ? 1 : 0;
  });
}

export function validateConstraints(
  document: DesignDocumentLike,
  constraints: readonly RuntimeConstraint[],
  options: {
    readonly operation?: DesignOperationLike;
    readonly phase?: ValidationPhase;
    readonly adapters?: ValidationAdapters;
    readonly policy?: ValidationPolicy;
    readonly forceFull?: boolean;
  } = {},
): ValidationReport {
  const phase = options.phase ?? "preflight";
  const policy = { ...DEFAULT_POLICY, ...(options.policy ?? {}) };
  if ((policy.max_auto_fix_rounds ?? 1) !== 1) {
    throw new Error("CONSTRAINT_VALIDATOR_REPAIR_LOOP_FORBIDDEN");
  }
  const adapters = options.adapters ?? {};
  const candidate = options.operation ? projectOperation(document, options.operation) : document;
  const impact = impactSet(
    candidate,
    options.operation,
    constraints,
    policy,
    options.forceFull === true || phase === "export",
  );
  const violations: ConstraintViolation[] = [];
  const validators = new Set<string>();
  for (const constraint of [...constraints]
    .filter((item) => item.active !== false)
    .sort((a, b) => a.constraint_id.localeCompare(b.constraint_id))) {
    for (const spec of VALIDATOR_SPECS) {
      if (!spec.constraintTypes.includes(constraint.type)) continue;
      if (spec.name === "LockedRegionValidator" && !lockApplies(constraint, options.operation)) {
        continue;
      }
      if (spec.name === "ExportDimensionValidator" && phase !== "export") continue;
      validators.add(spec.name);
      violations.push(...spec.fn(candidate, constraint, impact.nodeIds, adapters, policy));
    }
  }
  const ordered = sortViolations(violations);
  const blocking = ordered.filter((item) => item.blocking).length;
  const unavailable = ordered.some((item) => item.unavailable);
  const status = blocking
    ? "BLOCKED"
    : unavailable
      ? "VALIDATION_UNAVAILABLE"
      : ordered.length
        ? "WARN"
        : "PASS";
  return {
    status,
    violations: ordered,
    hard_pass: blocking === 0,
    health_score: healthScore(constraints, ordered),
    metrics: {
      validators_run: [...validators].sort(),
      nodes_scanned: impact.nodeIds.size,
      violations_count: ordered.length,
      blocking_count: blocking,
      fallback_full_scan: impact.fallbackFullScan,
    },
  };
}

export function validateBatch(
  document: DesignDocumentLike,
  constraints: readonly RuntimeConstraint[],
  operations: readonly DesignOperationLike[],
  options: {
    readonly adapters?: ValidationAdapters;
    readonly policy?: ValidationPolicy;
  } = {},
): ValidationReport {
  let working = document;
  const violations: ConstraintViolation[] = [];
  const validators = new Set<string>();
  let nodesScanned = 0;
  let fallback = false;
  for (const operation of operations) {
    const report = validateConstraints(working, constraints, {
      operation,
      ...(options.adapters ? { adapters: options.adapters } : {}),
      ...(options.policy ? { policy: options.policy } : {}),
    });
    violations.push(...report.violations);
    for (const validator of report.metrics.validators_run) validators.add(validator);
    nodesScanned += report.metrics.nodes_scanned;
    fallback ||= report.metrics.fallback_full_scan;
    working = projectOperation(working, operation);
  }
  const ordered = sortViolations(violations);
  const blocking = ordered.filter((item) => item.blocking).length;
  const unavailable = ordered.some((item) => item.unavailable);
  return {
    status: blocking
      ? "BLOCKED"
      : unavailable
        ? "VALIDATION_UNAVAILABLE"
        : ordered.length
          ? "WARN"
          : "PASS",
    violations: ordered,
    hard_pass: blocking === 0,
    health_score: healthScore(constraints, ordered),
    metrics: {
      validators_run: [...validators].sort(),
      nodes_scanned: nodesScanned,
      violations_count: ordered.length,
      blocking_count: blocking,
      fallback_full_scan: fallback,
    },
  };
}

export function validateExport(
  document: DesignDocumentLike,
  constraints: readonly RuntimeConstraint[],
  options: { readonly adapters?: ValidationAdapters; readonly policy?: ValidationPolicy } = {},
): ValidationReport {
  return validateConstraints(document, constraints, {
    phase: "export",
    forceFull: true,
    ...(options.adapters ? { adapters: options.adapters } : {}),
    ...(options.policy ? { policy: options.policy } : {}),
  });
}

export function reportToIrIssues(
  report: ValidationReport,
  operationId?: string,
): readonly IrIssueLike[] {
  return report.violations
    .filter((item) => item.blocking)
    .map((item) => ({
      code: "IR_CONSTRAINT_FAILED" as const,
      message: item.message,
      node_ids: item.affected_node_ids,
      ...(operationId ? { operation_id: operationId } : {}),
    }));
}

export function createIrPreflight(
  constraints: readonly RuntimeConstraint[],
  options: { readonly adapters?: ValidationAdapters; readonly policy?: ValidationPolicy } = {},
): (document: DesignDocumentLike, operation: DesignOperationLike) => readonly IrIssueLike[] {
  return (document, operation) =>
    reportToIrIssues(
      validateConstraints(document, constraints, {
        operation,
        ...(options.adapters ? { adapters: options.adapters } : {}),
        ...(options.policy ? { policy: options.policy } : {}),
      }),
      operation.operation_id,
    );
}
