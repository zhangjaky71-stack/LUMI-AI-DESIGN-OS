import type { QualityResult } from "./types";

export interface QualityMetricSnapshot {
  readonly attributes: Readonly<Record<string, string | number | boolean>>;
  readonly metrics: Readonly<Record<string, number>>;
}

/** Safe-by-default telemetry projection; no prompt text, image URL, OCR text or raw VLM output. */
export function qualityMetricSnapshot(result: QualityResult): QualityMetricSnapshot {
  return {
    attributes: {
      quality_result_id: result.quality_result_id,
      organization_id: result.organization_id,
      project_id: result.project_id,
      artifact_version_id: result.artifact_version_id,
      profile_id: result.profile_id,
      profile_version: result.profile_version,
      status: result.status,
      unavailable_grader_count: result.unavailable_graders.length,
    },
    metrics: {
      overall_score: result.overall_score,
      confidence: result.confidence,
      hard_violation_count: result.violations.filter((item) => item.severity === "HARD").length,
      repair_action_count: result.repair_actions.length,
      evidence_count: result.evidence.length,
      dimension_count: result.dimensions.length,
    },
  };
}
