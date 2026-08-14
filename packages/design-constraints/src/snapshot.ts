import { canonicalSha256, canonicalStringify } from "../../design-ir/src/index";
import { resolveConstraints } from "./resolver";
import type {
  ConstraintConflict,
  ConstraintSeverity,
  ConstraintType,
  DesignConstraint,
  DesignDocument,
} from "./types";

export interface ConstraintSnapshot {
  readonly document_id: string;
  readonly document_version: number;
  readonly effective_constraints: readonly DesignConstraint[];
  readonly conflicts: readonly ConstraintConflict[];
  readonly stale_constraint_ids: readonly string[];
}

export function buildConstraintSnapshot(
  document: DesignDocument,
  constraints: readonly DesignConstraint[],
): ConstraintSnapshot {
  const resolved = resolveConstraints(document, constraints);
  const documentVersion =
    typeof document.metadata.document_version === "number" ? document.metadata.document_version : 0;
  return {
    document_id: document.document_id,
    document_version: documentVersion,
    effective_constraints: [...resolved.constraints].sort((a, b) => a.id.localeCompare(b.id)),
    conflicts: [...resolved.conflicts],
    stale_constraint_ids: [...resolved.stale_constraint_ids],
  };
}

export function canonicalConstraintSnapshot(snapshot: ConstraintSnapshot): string {
  return canonicalStringify(snapshot);
}

export async function hashConstraintSnapshot(snapshot: ConstraintSnapshot): Promise<string> {
  return canonicalSha256(snapshot);
}

export interface CompactConstraintSummaryItem {
  readonly id: string;
  readonly type: ConstraintType;
  readonly severity: ConstraintSeverity;
  readonly node_ids: readonly string[];
  readonly parameters: Readonly<Record<string, unknown>>;
}

/** Compact deterministic summary for Agent planning; server-side validation remains authoritative. */
export function summarizeConstraintsForAgent(
  document: DesignDocument,
  constraints: readonly DesignConstraint[],
): readonly CompactConstraintSummaryItem[] {
  return resolveConstraints(document, constraints).constraints.map((constraint) => ({
    id: constraint.id,
    type: constraint.type,
    severity: constraint.severity,
    node_ids: [...(constraint.scope.node_ids ?? [])],
    parameters: constraint.parameters,
  }));
}
