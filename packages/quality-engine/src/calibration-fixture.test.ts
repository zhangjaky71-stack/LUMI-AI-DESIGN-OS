import { describe, expect, it } from "vitest";
import fixture from "../../../fixtures/quality/node-50-calibration.json";
import { validateCalibration } from "./calibration";

function metrics(threshold: number): { precision: number; recall: number; f1: number; false_positive_rate: number; false_negative_rate: number } {
  let tp = 0;
  let fp = 0;
  let tn = 0;
  let fn = 0;
  for (const sample of fixture.samples) {
    const predictedPass = sample.grader_score >= threshold;
    const actualPass = sample.human_label === "PASS";
    if (predictedPass && actualPass) tp += 1;
    else if (predictedPass) fp += 1;
    else if (actualPass) fn += 1;
    else tn += 1;
  }
  const precision = tp / (tp + fp);
  const recall = tp / (tp + fn);
  return {
    precision,
    recall,
    f1: (2 * precision * recall) / (precision + recall),
    false_positive_rate: fp / (fp + tn),
    false_negative_rate: fn / (fn + tp),
  };
}

describe("NODE-50 calibration corpus", () => {
  it("recomputes the pinned FP/FN metrics instead of trusting a narrative report", () => {
    const actual = metrics(fixture.threshold);
    expect(fixture.samples).toHaveLength(fixture.expected_metrics.sample_count);
    expect(actual.precision).toBeCloseTo(fixture.expected_metrics.precision, 12);
    expect(actual.recall).toBeCloseTo(fixture.expected_metrics.recall, 12);
    expect(actual.f1).toBeCloseTo(fixture.expected_metrics.f1, 12);
    expect(actual.false_positive_rate).toBeCloseTo(fixture.expected_metrics.false_positive_rate, 12);
    expect(actual.false_negative_rate).toBeCloseTo(fixture.expected_metrics.false_negative_rate, 12);
    expect(validateCalibration({
      grader_id: fixture.grader_id,
      grader_version: fixture.grader_version,
      dataset_version: fixture.dataset_version,
      sample_count: fixture.samples.length,
      precision: actual.precision,
      recall: actual.recall,
      f1: actual.f1,
      false_positive_rate: actual.false_positive_rate,
      false_negative_rate: actual.false_negative_rate,
      inter_rater_agreement: fixture.inter_rater_agreement,
      approved: true,
    }).approved).toBe(true);
  });

  it("does not allow an apparently approved but statistically weak calibration", () => {
    expect(() => validateCalibration({
      grader_id: "weak",
      grader_version: "1",
      dataset_version: "d",
      sample_count: 40,
      precision: 0.5,
      recall: 0.5,
      f1: 0.5,
      false_positive_rate: 0.5,
      false_negative_rate: 0.5,
      inter_rater_agreement: 0.4,
      approved: true,
    })).toThrow("QUALITY_CALIBRATION_APPROVAL_METRICS_TOO_LOW");
  });
});
