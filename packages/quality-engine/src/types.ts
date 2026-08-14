import type { DesignDocument, DesignOperation, JsonValue } from "../../design-ir/src/index";
import type { ConstraintViolation } from "../../design-constraints/src/index";

export const QUALITY_DIMENSIONS = [
  "CONSTRAINT_COMPLIANCE",
  "COMPOSITION",
  "VISUAL_HIERARCHY",
  "ALIGNMENT_SPACING",
  "TYPOGRAPHY_READABILITY",
  "CONTRAST",
  "BRAND_CONSISTENCY",
  "IDENTITY_CONSISTENCY",
  "TEXT_ACCURACY",
  "LOGO_INTEGRITY",
  "QR_READABILITY",
  "IMAGE_DEFECTS",
  "RESOLUTION_EXPORT_READINESS",
] as const;
export type QualityDimension = (typeof QUALITY_DIMENSIONS)[number];

export const QUALITY_STATUSES = ["PASS", "PASS_WITH_WARNINGS", "FAIL_REPAIRABLE", "FAIL_HARD", "REVIEW_REQUIRED"] as const;
export type QualityStatus = (typeof QUALITY_STATUSES)[number];
export type QualitySeverity = "HARD" | "MAJOR" | "MINOR" | "ADVISORY";
export type EvidenceKind = "DETERMINISTIC" | "CONSTRAINT" | "BRAND" | "IDENTITY" | "OCR" | "QR" | "IMAGE_METADATA" | "VISUAL_GRADER" | "HUMAN_CALIBRATION";

export interface QualityEvidence {
  readonly evidence_id: string;
  readonly kind: EvidenceKind;
  readonly source: string;
  readonly source_version: string;
  readonly confidence: number;
  readonly ref?: string;
  readonly data?: Readonly<Record<string, JsonValue>>;
}

export interface QualityDimensionResult {
  readonly dimension: QualityDimension;
  readonly score: number;
  readonly confidence: number;
  readonly threshold: number;
  readonly weight: number;
  readonly severity: QualitySeverity;
  readonly hard_gate: boolean;
  readonly passed: boolean;
  readonly evidence_ids: readonly string[];
  readonly reason_codes: readonly string[];
}

export interface QualityViolation {
  readonly violation_id: string;
  readonly dimension: QualityDimension;
  readonly severity: QualitySeverity;
  readonly reason_code: string;
  readonly message: string;
  readonly target_id?: string;
  readonly evidence_ids: readonly string[];
  readonly repairable: boolean;
  readonly source_constraint?: ConstraintViolation;
}

export interface QualityProfileDimension {
  readonly dimension: QualityDimension;
  readonly weight: number;
  readonly threshold: number;
  readonly hard_gate: boolean;
  readonly minimum_confidence: number;
}

export interface QualityProfile {
  readonly profile_id: string;
  readonly version: string;
  readonly name: "exploration" | "production-web" | "brand-strict" | "product-strict" | "print" | "social-fast";
  readonly overall_pass_threshold: number;
  readonly overall_warning_threshold: number;
  readonly review_confidence_threshold: number;
  readonly dimensions: readonly QualityProfileDimension[];
}

export interface VisualGradeDimension {
  readonly dimension: Extract<QualityDimension, "COMPOSITION" | "VISUAL_HIERARCHY" | "IMAGE_DEFECTS" | "TYPOGRAPHY_READABILITY">;
  readonly score: number;
  readonly confidence: number;
  readonly reason_codes: readonly string[];
  readonly evidence_ref?: string;
}

export interface VisualGradeResult {
  readonly grader_id: string;
  readonly grader_version: string;
  readonly model_provider: string;
  readonly model_name: string;
  readonly model_version: string;
  readonly calibration_dataset_version: string;
  readonly prompt_version: string;
  readonly dimensions: readonly VisualGradeDimension[];
  readonly strengths: readonly string[];
  readonly raw_evidence_ref?: string;
}

export interface CriticSubject {
  readonly organization_id: string;
  readonly project_id: string;
  readonly artifact_id: string;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly design_document: DesignDocument;
  readonly rendered_asset_ref: string;
  readonly width?: number;
  readonly height?: number;
  readonly expected_text?: readonly string[];
  readonly metadata?: Readonly<Record<string, JsonValue>>;
}

export interface DeterministicSignal {
  readonly dimension: QualityDimension;
  readonly score: number;
  readonly confidence: number;
  readonly severity: QualitySeverity;
  readonly hard_fail: boolean;
  readonly reason_codes: readonly string[];
  readonly evidence: readonly QualityEvidence[];
  readonly violations?: readonly QualityViolation[];
  readonly repair_operations?: readonly DesignOperation[];
}

export interface QualityResult {
  readonly quality_result_id: string;
  readonly organization_id: string;
  readonly project_id: string;
  readonly artifact_id: string;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly profile_id: string;
  readonly profile_version: string;
  readonly status: QualityStatus;
  readonly overall_score: number;
  readonly confidence: number;
  readonly dimensions: readonly QualityDimensionResult[];
  readonly violations: readonly QualityViolation[];
  readonly strengths: readonly string[];
  readonly repair_actions: readonly DesignOperation[];
  readonly evidence: readonly QualityEvidence[];
  readonly unavailable_graders: readonly string[];
  readonly grader_versions: Readonly<Record<string, string>>;
  readonly created_at: string;
}

export interface HumanCalibrationSummary {
  readonly grader_id: string;
  readonly grader_version: string;
  readonly dataset_version: string;
  readonly sample_count: number;
  readonly precision: number;
  readonly recall: number;
  readonly f1: number;
  readonly false_positive_rate: number;
  readonly false_negative_rate: number;
  readonly inter_rater_agreement: number;
  readonly approved: boolean;
}
