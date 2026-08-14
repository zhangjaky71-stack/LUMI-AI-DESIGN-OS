import type { ConstraintViolation, PostflightDecision, PreflightDecision } from "./types";

const SEVERITY_RANK = { HARD: 3, SOFT: 2, ADVISORY: 1 } as const;

function key(violation: ConstraintViolation): string {
  return [
    violation.constraint_id,
    violation.target_id ?? "",
    violation.validator,
    violation.reason_code,
  ].join("|");
}

/** Collapse duplicate evidence from one root cause while preserving the strongest violation. */
export function aggregateViolations(
  violations: readonly ConstraintViolation[],
): readonly ConstraintViolation[] {
  const byKey = new Map<string, ConstraintViolation>();
  for (const violation of violations) {
    const current = byKey.get(key(violation));
    if (!current) {
      byKey.set(key(violation), violation);
      continue;
    }
    const stronger = SEVERITY_RANK[violation.severity] > SEVERITY_RANK[current.severity];
    const higherScore = (violation.score ?? Number.NEGATIVE_INFINITY) > (current.score ?? Number.NEGATIVE_INFINITY);
    if (stronger || (!stronger && higherScore)) byKey.set(key(violation), violation);
  }
  return [...byKey.values()].sort((left, right) => {
    const severity = SEVERITY_RANK[right.severity] - SEVERITY_RANK[left.severity];
    if (severity) return severity;
    return key(left).localeCompare(key(right));
  });
}

export function preflightDecision(violations: readonly ConstraintViolation[]): PreflightDecision {
  if (violations.some((violation) => violation.severity === "HARD")) return "DENY";
  if (violations.length) return "ALLOW_WITH_WARNINGS";
  return "ALLOW";
}

export function postflightDecision(violations: readonly ConstraintViolation[]): PostflightDecision {
  if (violations.some((violation) => violation.severity === "HARD")) return "FAIL";
  if (violations.some((violation) => violation.severity === "SOFT")) return "REPAIR";
  return "PASS";
}
