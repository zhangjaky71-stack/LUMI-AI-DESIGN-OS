import { validateConstraints } from "./runtime";
import type {
  ConstraintViolation,
  DesignDocumentLike,
  DesignOperationLike,
  RuntimeConstraint,
  ValidationAdapters,
  ValidationPolicy,
  ValidationReport,
} from "./types";

const FORBIDDEN = new Set([
  "ProtectedRegionValidator",
  "BrandTokenValidator",
  "IdentityPreservationValidator",
]);

export function proposeFixOperations(
  violations: readonly ConstraintViolation[],
  documentVersion: number,
): readonly DesignOperationLike[] {
  const values: DesignOperationLike[] = [];
  for (const item of violations) {
    if (FORBIDDEN.has(item.validator) || !item.affected_node_ids.length) continue;
    const nodeId = item.affected_node_ids[0]!;
    const suffix = item.violation_id.slice(-12);
    if (
      ["BoundsValidator", "SafeAreaValidator"].includes(item.validator) &&
      Array.isArray(item.expected_value)
    ) {
      values.push({
        operation_id: `autofix:${suffix}:move`,
        type: "MOVE_NODE",
        target_ids: [nodeId],
        expected_document_version: documentVersion,
        payload: { x: item.expected_value[0], y: item.expected_value[1] },
        reason: "constraint-validator-safe-autofix",
      });
    } else if (item.validator === "FontSizeValidator" && typeof item.expected_value === "number") {
      values.push({
        operation_id: `autofix:${suffix}:font`,
        type: "SET_PROPERTY",
        target_ids: [nodeId],
        expected_document_version: documentVersion,
        payload: { property: "font_size", value: item.expected_value },
        reason: "constraint-validator-safe-autofix",
      });
    } else if (item.validator === "AspectRatioValidator" && typeof item.expected_value === "number") {
      values.push({
        operation_id: `autofix:${suffix}:ratio`,
        type: "RESIZE_NODE",
        target_ids: [nodeId],
        expected_document_version: documentVersion,
        payload: { width: item.expected_value * 100, height: 100 },
        reason: "constraint-validator-safe-autofix",
      });
    }
  }
  return values;
}

export function validateProposedFix(
  document: DesignDocumentLike,
  constraints: readonly RuntimeConstraint[],
  operation: DesignOperationLike,
  options: { readonly adapters?: ValidationAdapters; readonly policy?: ValidationPolicy } = {},
): ValidationReport {
  return validateConstraints(document, constraints, {
    operation,
    ...(options.adapters ? { adapters: options.adapters } : {}),
    ...(options.policy ? { policy: options.policy } : {}),
  });
}

export function validateProposedFixWithIrRuntime(
  document: DesignDocumentLike,
  constraints: readonly RuntimeConstraint[],
  operation: DesignOperationLike,
  applyIrRuntime: (document: DesignDocumentLike, operation: DesignOperationLike) => DesignDocumentLike,
  options: { readonly adapters?: ValidationAdapters; readonly policy?: ValidationPolicy } = {},
): ValidationReport {
  const candidate = applyIrRuntime(document, operation);
  return validateConstraints(candidate, constraints, {
    forceFull: true,
    ...(options.adapters ? { adapters: options.adapters } : {}),
    ...(options.policy ? { policy: options.policy } : {}),
  });
}
