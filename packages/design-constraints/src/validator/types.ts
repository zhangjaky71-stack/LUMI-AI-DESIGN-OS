export type ConstraintSeverity = "HARD" | "SOFT" | "ADVISORY";
export type ValidationPhase = "preflight" | "postflight" | "export";
export type ValidationStatus = "PASS" | "WARN" | "BLOCKED" | "VALIDATION_UNAVAILABLE";

export interface DesignNodeLike {
  readonly id: string;
  readonly kind: string;
  readonly parent_id: string | null;
  readonly children: readonly string[];
  readonly [key: string]: unknown;
}

export interface DesignDocumentLike {
  readonly schema_version: string;
  readonly document_id: string;
  readonly root_id: string;
  readonly nodes: Readonly<Record<string, DesignNodeLike>>;
  readonly metadata: Readonly<Record<string, unknown>>;
  readonly [key: string]: unknown;
}

export interface DesignOperationLike {
  readonly operation_id: string;
  readonly type: string;
  readonly target_ids: readonly string[];
  readonly expected_document_version?: number;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly reason?: string;
}

export interface RuntimeScope {
  readonly node_ids?: readonly string[];
  readonly semantic_tags?: readonly string[];
  readonly region?: Readonly<Record<string, number>>;
}

export interface RuntimeConstraint {
  readonly constraint_id: string;
  readonly type: string;
  readonly severity: ConstraintSeverity;
  readonly scope?: RuntimeScope;
  readonly parameters?: Readonly<Record<string, unknown>>;
  readonly active?: boolean;
}

export interface ValidationPolicy {
  readonly incremental_full_scan_ratio?: number;
  readonly incremental_full_scan_node_limit?: number;
  readonly unavailable_hard_blocks?: boolean;
  readonly max_auto_fix_rounds?: 1;
}

export interface ValidationAdapters {
  readonly text_measure?: (node: DesignNodeLike) => Readonly<Record<string, number>>;
  readonly qr_decode?: (node: DesignNodeLike) => boolean;
  readonly identity_score?: (node: DesignNodeLike) => number | null;
}

export interface ConstraintViolation {
  readonly violation_id: string;
  readonly constraint_id: string;
  readonly type: string;
  readonly validator: string;
  readonly severity: ConstraintSeverity;
  readonly affected_node_ids: readonly string[];
  readonly message: string;
  readonly measured_value?: unknown;
  readonly expected_value?: unknown;
  readonly suggested_fix_operations?: readonly Readonly<Record<string, unknown>>[];
  readonly blocking: boolean;
  readonly unavailable: boolean;
}

export interface ValidationMetrics {
  readonly validators_run: readonly string[];
  readonly nodes_scanned: number;
  readonly violations_count: number;
  readonly blocking_count: number;
  readonly fallback_full_scan: boolean;
}

export interface ValidationReport {
  readonly status: ValidationStatus;
  readonly violations: readonly ConstraintViolation[];
  readonly hard_pass: boolean;
  readonly health_score: number;
  readonly metrics: ValidationMetrics;
}

export interface IrIssueLike {
  readonly code: "IR_CONSTRAINT_FAILED";
  readonly message: string;
  readonly node_ids?: readonly string[];
  readonly operation_id?: string;
}

export const P0_VALIDATORS = [
  "BoundsValidator",
  "SafeAreaValidator",
  "LockedRegionValidator",
  "TextOverflowValidator",
  "FontSizeValidator",
  "AspectRatioValidator",
  "ContrastValidator",
  "ProtectedRegionValidator",
  "QRValidator",
  "BrandTokenValidator",
  "IdentityPreservationValidator",
  "ExportDimensionValidator",
] as const;
