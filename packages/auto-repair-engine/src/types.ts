import type { DesignConstraint, DesignDocument, DesignOperation } from "../../design-constraints/src/index";
import type { CriticSubject, QualityResult } from "../../quality-engine/src/index";

export const REPAIR_ACTION_KINDS = [
  "STRUCTURAL_DESIGN_OP",
  "LOCAL_IMAGE_EDIT",
  "REGENERATE_ELEMENT",
  "REGENERATE_ARTIFACT",
  "RESOLUTION_UPSCALE",
  "MANUAL_REVIEW",
] as const;
export type RepairActionKind = (typeof REPAIR_ACTION_KINDS)[number];

export const REPAIR_LOOP_STATUSES = [
  "SUCCEEDED",
  "REVIEW_REQUIRED",
  "BUDGET_EXHAUSTED",
  "ITERATION_LIMIT",
  "STALE_SOURCE",
  "NO_SAFE_REPAIR",
  "FAILED",
] as const;
export type RepairLoopStatus = (typeof REPAIR_LOOP_STATUSES)[number];

export type RepairCandidateDisposition = "PROMOTED_READY" | "PROMOTED_DRAFT" | "REJECTED" | "REVIEW";

export interface AutoRepairPolicy {
  readonly policy_id: string;
  readonly version: string;
  readonly max_auto_repair_iterations: number;
  readonly max_repair_cost_usd: string;
  readonly minimum_expected_gain: number;
  readonly max_score_regression: number;
}

export interface RepairSource {
  readonly branch_id: string;
  readonly expected_branch_head: string;
  readonly subject: CriticSubject;
  readonly quality: QualityResult;
  readonly constraints: readonly DesignConstraint[];
}

export interface RepairPlanItem {
  readonly item_id: string;
  readonly fingerprint: string;
  readonly kind: RepairActionKind;
  readonly priority: number;
  readonly reversible: boolean;
  readonly paid: boolean;
  readonly estimated_cost_usd: string;
  readonly expected_gain: number;
  readonly reason_codes: readonly string[];
  readonly target_ids: readonly string[];
  readonly operations?: readonly DesignOperation[];
}

export interface RepairPlan {
  readonly plan_id: string;
  readonly source_quality_result_id: string;
  readonly source_artifact_version_id: string;
  readonly source_design_document_version_id: string;
  readonly policy_id: string;
  readonly policy_version: string;
  readonly iteration: number;
  readonly items: readonly RepairPlanItem[];
}

export interface CandidateMaterialization {
  readonly design_document: DesignDocument;
  readonly rendered_asset_ref: string;
  readonly content_hash: string;
  readonly constraint_snapshot_hash: string;
  readonly width?: number;
  readonly height?: number;
  readonly actual_cost_usd: string;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface PersistedRepairCandidate extends CandidateMaterialization {
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly branch_id: string;
  readonly source_artifact_version_id: string;
}

export interface RepairAttemptRecord {
  readonly loop_id: string;
  readonly iteration: number;
  readonly plan_item_id: string;
  readonly action_kind: RepairActionKind;
  readonly source_artifact_version_id: string;
  readonly candidate_artifact_version_id?: string;
  readonly source_quality_result_id: string;
  readonly candidate_quality_result_id?: string;
  readonly before_score: number;
  readonly after_score?: number;
  readonly score_gain?: number;
  readonly cost_usd: string;
  readonly disposition: RepairCandidateDisposition;
  readonly reason_codes: readonly string[];
  readonly created_at: string;
}

export interface RepairLoopResult {
  readonly loop_id: string;
  readonly status: RepairLoopStatus;
  readonly initial_artifact_version_id: string;
  readonly final_artifact_version_id: string;
  readonly initial_quality_result_id: string;
  readonly final_quality_result_id: string;
  readonly iterations: number;
  readonly spent_usd: string;
  readonly attempts: readonly RepairAttemptRecord[];
  readonly reason_codes: readonly string[];
}

export interface QualityComparison {
  readonly disposition: RepairCandidateDisposition;
  readonly score_gain: number;
  readonly new_hard_violations: readonly string[];
  readonly reason_codes: readonly string[];
}
