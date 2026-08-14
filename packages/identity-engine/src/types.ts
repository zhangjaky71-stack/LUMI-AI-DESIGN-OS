import type { ConstraintSeverity, DesignConstraint, PostflightArtifactRef, PostflightContext } from "../../design-constraints/src/types";

export const IDENTITY_TYPES = ["PRODUCT", "LOGO", "CHARACTER", "FACE", "STYLE_REFERENCE"] as const;
export type IdentityType = (typeof IDENTITY_TYPES)[number];

export const IDENTITY_SCENARIOS = [
  "STRICT_PRESERVE",
  "BACKGROUND_REPLACEMENT",
  "CREATIVE_REDRAW",
  "STYLE_REFERENCE",
] as const;
export type IdentityScenario = (typeof IDENTITY_SCENARIOS)[number];

export type IdentityReferenceSetStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";
export type CalibrationProfileStatus = "DRAFT" | "PUBLISHED" | "RETIRED";
export type CalibrationLabel = "POSITIVE" | "NEGATIVE" | "NEAR_MISS";
export type IdentityValidationStatus = "PASS" | "FAIL" | "REVIEW" | "UNAVAILABLE";

export interface IdentityRegion {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
  readonly coordinate_space: "NORMALIZED" | "PIXELS";
}

export interface IdentityReferenceView {
  readonly view_id: string;
  readonly asset_id: string;
  readonly asset_version: string;
  readonly organization_id: string;
  readonly role?: "CANONICAL" | "FRONT" | "BACK" | "SIDE" | "DETAIL" | "WORDMARK" | "OTHER";
  readonly region?: IdentityRegion;
  readonly checksum_sha256?: string;
  readonly notes?: string;
}

export interface FaceReferencePolicy {
  readonly explicit_processing_consent: boolean;
  readonly purpose: string;
  readonly retention_until: string;
  readonly persistent_biometric_index: false;
}

export interface IdentityReferenceSet {
  readonly identity_id: string;
  readonly organization_id: string;
  readonly project_id?: string;
  readonly brand_id?: string;
  readonly type: IdentityType;
  readonly canonical_asset_ids: readonly string[];
  readonly reference_views: readonly IdentityReferenceView[];
  readonly notes?: string;
  readonly threshold_profile_id: string;
  readonly threshold_profile_version: string;
  readonly version: string;
  readonly status: IdentityReferenceSetStatus;
  readonly face_policy?: FaceReferencePolicy;
}

export type IdentityAssetRights = "USER_OWNED" | "LICENSED" | "UNKNOWN";

/**
 * NODE-18 boundary. Identity Engine consumes verified READY assets and never
 * interprets an upload as verified merely because the caller supplied an id.
 */
export interface VerifiedIdentityAsset {
  readonly asset_id: string;
  readonly asset_version: string;
  readonly organization_id: string;
  readonly state: "READY";
  readonly checksum_sha256: string;
  readonly mime_type: string;
  readonly rights: IdentityAssetRights;
  readonly width?: number;
  readonly height?: number;
  readonly bytes_ref?: string;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface CalibrationSample {
  readonly sample_id: string;
  readonly identity_type: IdentityType;
  readonly label: CalibrationLabel;
  readonly score: number;
  readonly scenario: IdentityScenario;
  readonly notes?: string;
}

export interface CalibrationMetrics {
  readonly threshold: number;
  readonly precision: number;
  readonly recall: number;
  readonly f1: number;
  readonly false_positive_rate: number;
  readonly false_negative_rate: number;
  readonly roc_auc: number;
  readonly average_precision: number;
  readonly positive_count: number;
  readonly negative_count: number;
  readonly near_miss_count: number;
}

export interface ThresholdCalibrationProfile {
  readonly profile_id: string;
  readonly organization_id: string;
  readonly identity_type: IdentityType;
  readonly scenario: IdentityScenario;
  readonly version: string;
  readonly status: CalibrationProfileStatus;
  readonly threshold: number;
  readonly review_floor: number;
  readonly minimum_confidence: number;
  readonly signal_weights: Readonly<Record<string, number>>;
  readonly required_signals: readonly string[];
  readonly model_bundle_version: string;
  readonly preprocessor_version: string;
  readonly calibration_dataset_version: string;
  readonly metrics: CalibrationMetrics;
}

export interface CalibrationObjective {
  readonly minimum_precision?: number;
  readonly minimum_recall?: number;
  readonly prefer_higher_threshold_on_tie?: boolean;
}

export interface IdentityEvidenceRef {
  readonly kind: "ASSET" | "REGION" | "OCR" | "FEATURE" | "MODEL" | "CALIBRATION" | "HASH";
  readonly ref: string;
  readonly region?: IdentityRegion;
  readonly detail?: string;
}

export interface IdentitySignalScore {
  readonly signal: string;
  readonly score: number;
  readonly confidence: number;
  readonly reference_view_id?: string;
  readonly evidence_refs: readonly IdentityEvidenceRef[];
}

export interface IdentityCandidate {
  readonly organization_id: string;
  readonly artifact: PostflightArtifactRef;
  readonly target_region?: IdentityRegion;
  readonly target_node_id?: string;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface IdentitySignalRequest {
  readonly identity: IdentityReferenceSet;
  readonly references: readonly VerifiedIdentityAsset[];
  readonly candidate: IdentityCandidate;
  readonly profile: ThresholdCalibrationProfile;
}

export interface IdentitySignalProvider {
  readonly provider_id: string;
  readonly provider_version: string;
  readonly preprocessor_version: string;
  score(request: IdentitySignalRequest): Promise<readonly IdentitySignalScore[]>;
}

export interface IdentityValidationReport {
  readonly report_id: string;
  readonly organization_id: string;
  readonly identity_id: string;
  readonly identity_type: IdentityType;
  readonly severity: ConstraintSeverity;
  readonly scenario: IdentityScenario;
  readonly status: IdentityValidationStatus;
  readonly identity_score: number | null;
  readonly confidence: number;
  readonly threshold: number;
  readonly review_floor: number;
  readonly signal_scores: readonly IdentitySignalScore[];
  readonly reference_set_version: string;
  readonly threshold_profile_id: string;
  readonly threshold_profile_version: string;
  readonly calibration_dataset_version: string;
  readonly provider_id: string;
  readonly provider_version: string;
  readonly preprocessor_version: string;
  readonly evidence_refs: readonly IdentityEvidenceRef[];
  readonly candidate_region?: IdentityRegion;
  readonly reason_code?: string;
  readonly identity_validation_snapshot_id: string;
}

export interface IdentityValidationInput {
  readonly identity: IdentityReferenceSet;
  readonly profile: ThresholdCalibrationProfile;
  readonly candidate: IdentityCandidate;
  readonly references: readonly VerifiedIdentityAsset[];
  readonly severity: ConstraintSeverity;
  readonly scenario: IdentityScenario;
}

export interface IdentityReferenceResolver {
  resolve(identity: IdentityReferenceSet): Promise<readonly VerifiedIdentityAsset[]>;
}

export interface IdentityPostflightResolver {
  validate(context: PostflightContext, constraint: DesignConstraint): Promise<IdentityValidationReport>;
}

export interface IdentityPrivacyPolicy {
  readonly allow_face_processing: boolean;
  readonly allow_persistent_face_index: false;
  readonly cross_tenant_face_index: false;
}
