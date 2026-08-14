import type {
  ConstraintOverrideToken,
  DesignConstraint,
  DesignDocument,
} from "./types";

export interface OverrideValidation {
  readonly valid: boolean;
  readonly reason_code?: string;
}

export function validateOverride(
  document: DesignDocument,
  constraint: DesignConstraint,
  token: ConstraintOverrideToken,
  now = new Date(),
): OverrideValidation {
  if (constraint.source === "SAFETY_SYSTEM") {
    return { valid: false, reason_code: "SAFETY_CONSTRAINT_NOT_OVERRIDABLE" };
  }
  if (token.constraint_id !== constraint.id) {
    return { valid: false, reason_code: "OVERRIDE_CONSTRAINT_MISMATCH" };
  }
  if (token.document_id !== document.document_id) {
    return { valid: false, reason_code: "OVERRIDE_DOCUMENT_MISMATCH" };
  }
  const version =
    typeof document.metadata.document_version === "number" ? document.metadata.document_version : 0;
  if (token.document_version !== version) {
    return { valid: false, reason_code: "OVERRIDE_STALE_VERSION" };
  }
  if (!token.actor.trim() || !token.reason.trim()) {
    return { valid: false, reason_code: "OVERRIDE_AUDIT_FIELDS_REQUIRED" };
  }
  if (token.one_time && token.consumed) {
    return { valid: false, reason_code: "OVERRIDE_ALREADY_CONSUMED" };
  }
  if (token.expires_at) {
    const expiry = Date.parse(token.expires_at);
    if (!Number.isFinite(expiry) || expiry <= now.getTime()) {
      return { valid: false, reason_code: "OVERRIDE_EXPIRED" };
    }
  }
  return { valid: true };
}

export function isConstraintOverridden(
  document: DesignDocument,
  constraint: DesignConstraint,
  tokens: readonly ConstraintOverrideToken[] = [],
  now = new Date(),
): boolean {
  return tokens.some((token) => validateOverride(document, constraint, token, now).valid);
}
