import type { ConstraintViolation, RuntimeConstraint, ValidationPolicy } from "./types";

function canonicalPayload(
  constraintId: string,
  validator: string,
  nodeIds: readonly string[],
  messageCode: string,
): string {
  return JSON.stringify({
    affected_node_ids: [...nodeIds].sort(),
    constraint_id: constraintId,
    message_code: messageCode,
    validator,
  });
}

export function stableViolationId(
  constraintId: string,
  validator: string,
  nodeIds: readonly string[],
  messageCode: string,
): string {
  const bytes = new TextEncoder().encode(
    canonicalPayload(constraintId, validator, nodeIds, messageCode),
  );
  let value = 0xcbf29ce484222325n;
  const prime = 0x100000001b3n;
  const mask = 0xffffffffffffffffn;
  for (const byte of bytes) value = ((value ^ BigInt(byte)) * prime) & mask;
  return `cv1-${value.toString(16).padStart(16, "0")}`;
}

export function violation(
  constraint: RuntimeConstraint,
  validator: string,
  nodeIds: readonly string[],
  messageCode: string,
  message: string,
  policy: ValidationPolicy,
  options: {
    readonly measured?: unknown;
    readonly expected?: unknown;
    readonly unavailable?: boolean;
  } = {},
): ConstraintViolation {
  const unavailable = options.unavailable ?? false;
  const hardBlocks = policy.unavailable_hard_blocks ?? true;
  const blocking = constraint.severity === "HARD" && (!unavailable || hardBlocks);
  return {
    violation_id: stableViolationId(
      constraint.constraint_id,
      validator,
      nodeIds,
      messageCode,
    ),
    constraint_id: constraint.constraint_id,
    type: constraint.type,
    validator,
    severity: constraint.severity,
    affected_node_ids: [...nodeIds].sort(),
    message,
    blocking,
    unavailable,
    ...(options.measured !== undefined ? { measured_value: options.measured } : {}),
    ...(options.expected !== undefined ? { expected_value: options.expected } : {}),
  };
}
