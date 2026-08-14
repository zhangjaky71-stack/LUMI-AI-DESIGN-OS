import type { HumanCalibrationSummary, VisualGradeResult } from "./types";

function probability(value: number, label: string): void {
  if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error(`QUALITY_CALIBRATION_${label}_INVALID`);
}

export function validateCalibration(summary: HumanCalibrationSummary): HumanCalibrationSummary {
  if (!summary.grader_id || !summary.grader_version || !summary.dataset_version) throw new Error("QUALITY_CALIBRATION_IDENTITY_REQUIRED");
  if (!Number.isInteger(summary.sample_count) || summary.sample_count < 20) throw new Error("QUALITY_CALIBRATION_SAMPLE_COUNT_TOO_SMALL");
  probability(summary.precision, "PRECISION");
  probability(summary.recall, "RECALL");
  probability(summary.f1, "F1");
  probability(summary.false_positive_rate, "FPR");
  probability(summary.false_negative_rate, "FNR");
  probability(summary.inter_rater_agreement, "AGREEMENT");
  if (summary.approved && (summary.f1 < 0.6 || summary.inter_rater_agreement < 0.5)) {
    throw new Error("QUALITY_CALIBRATION_APPROVAL_METRICS_TOO_LOW");
  }
  return summary;
}

export function assertGradeCalibration(grade: VisualGradeResult, calibration: HumanCalibrationSummary): void {
  validateCalibration(calibration);
  if (!calibration.approved) throw new Error("QUALITY_GRADER_CALIBRATION_NOT_APPROVED");
  if (grade.grader_id !== calibration.grader_id || grade.grader_version !== calibration.grader_version) {
    throw new Error("QUALITY_GRADER_VERSION_NOT_CALIBRATED");
  }
  if (grade.calibration_dataset_version !== calibration.dataset_version) {
    throw new Error("QUALITY_GRADER_DATASET_VERSION_NOT_CALIBRATED");
  }
}
