import type {
  DesignDocument,
  DesignOperation,
  ExecutionResult,
  JsonValue,
} from "../../design-ir/src/index";

export type { DesignDocument, DesignOperation, ExecutionResult, JsonValue };

export const CONSTRAINT_SEVERITIES = ["HARD", "SOFT", "ADVISORY"] as const;
export type ConstraintSeverity = (typeof CONSTRAINT_SEVERITIES)[number];

export const CONSTRAINT_SOURCES = [
  "SAFETY_SYSTEM",
  "USER_EXPLICIT",
  "APPROVED_BRAND_RULE",
  "PROJECT_RULE",
  "RECIPE_RULE",
  "AGENT_INFERRED",
  "STYLE_PREFERENCE",
] as const;
export type ConstraintSource = (typeof CONSTRAINT_SOURCES)[number];

export const CONSTRAINT_TYPES = [
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
  "LOCK_IDENTITY",
  "LOCK_STYLE",
  "LOCK_BRAND",
  "PROTECT_REGION",
  "MUST_STAY_INSIDE",
  "MUST_NOT_OVERLAP",
  "MIN_MARGIN",
  "SAFE_AREA",
  "REQUIRE_CONTRAST",
  "REQUIRE_SCANNABILITY",
  "REQUIRE_TEXT_READABILITY",
  "REQUIRE_BRAND_COMPLIANCE",
  "REQUIRE_RESOLUTION",
  "REQUIRE_IDENTITY_SCORE",
] as const;
export type ConstraintType = (typeof CONSTRAINT_TYPES)[number];

export interface NormalizedRect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface ConstraintScope {
  readonly node_ids?: readonly string[];
  readonly frame_id?: string;
  readonly region?: NormalizedRect;
}

export interface DesignConstraint {
  readonly id: string;
  readonly type: ConstraintType;
  readonly scope: ConstraintScope;
  readonly severity: ConstraintSeverity;
  readonly source: ConstraintSource;
  readonly priority: number;
  readonly parameters: Readonly<Record<string, JsonValue>>;
  readonly active: boolean;
  /** Optional snapshot guard: stale rules must not silently evaluate a newer document. */
  readonly document_version?: number;
}

export interface ToleranceProfile {
  readonly position_px: number;
  readonly size_px: number;
  readonly rotation_deg: number;
  readonly aspect_ratio: number;
  readonly overlap_px: number;
}

export const DEFAULT_TOLERANCE: ToleranceProfile = Object.freeze({
  position_px: 0.25,
  size_px: 0.25,
  rotation_deg: 0.05,
  aspect_ratio: 0.001,
  overlap_px: 0.25,
});

export interface ConstraintViolation {
  readonly constraint_id: string;
  readonly type: ConstraintType;
  readonly severity: ConstraintSeverity;
  readonly validator: string;
  readonly reason_code: string;
  readonly target_id?: string;
  readonly score?: number;
  readonly threshold?: number;
  readonly expected?: JsonValue;
  readonly actual?: JsonValue;
  readonly repair_hint?: Readonly<Record<string, JsonValue>>;
  readonly raw_evidence_ref?: string;
}

export interface ConstraintConflict {
  readonly constraint_ids: readonly string[];
  readonly reason_code: "CONSTRAINT_CONFLICT";
  readonly target_ids: readonly string[];
}

export interface ConstraintOverrideToken {
  readonly token_id: string;
  readonly constraint_id: string;
  readonly document_id: string;
  readonly document_version: number;
  readonly actor: string;
  readonly reason: string;
  readonly expires_at?: string;
  readonly one_time?: boolean;
  readonly consumed?: boolean;
}

export type PreflightDecision = "ALLOW" | "ALLOW_WITH_WARNINGS" | "DENY";
export type PostflightDecision = "PASS" | "REPAIR" | "FAIL";

export interface PreflightReport {
  readonly decision: PreflightDecision;
  readonly violations: readonly ConstraintViolation[];
  readonly conflicts: readonly ConstraintConflict[];
  readonly effective_constraint_ids: readonly string[];
}

export interface GuardedExecutionResult {
  readonly preflight: PreflightReport;
  readonly execution?: ExecutionResult;
}

export interface PostflightArtifactRef {
  readonly artifact_id: string;
  readonly version: string;
  readonly mime_type?: string;
  readonly width?: number;
  readonly height?: number;
  readonly bytes_ref?: string;
  readonly metadata?: Readonly<Record<string, JsonValue>>;
}

export interface PostflightContext {
  readonly document: DesignDocument;
  readonly constraints: readonly DesignConstraint[];
  readonly before_ref: PostflightArtifactRef;
  readonly after_ref: PostflightArtifactRef;
  readonly overrides?: readonly ConstraintOverrideToken[];
}

export interface PostflightEvaluator {
  readonly name: string;
  readonly supported_types: readonly ConstraintType[];
  readonly supports_preflight: boolean;
  readonly supports_postflight: boolean;
  evaluate(context: PostflightContext, constraint: DesignConstraint): Promise<readonly ConstraintViolation[]>;
}

export interface PostflightReport {
  readonly decision: PostflightDecision;
  readonly violations: readonly ConstraintViolation[];
  readonly unavailable_validators: readonly string[];
}

export interface BrandComplianceValidator {
  validate(context: PostflightContext, constraint: DesignConstraint): Promise<readonly ConstraintViolation[]>;
}

export interface IdentitySimilarityValidator {
  validate(context: PostflightContext, constraint: DesignConstraint): Promise<readonly ConstraintViolation[]>;
}
