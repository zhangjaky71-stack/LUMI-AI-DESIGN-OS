import type {
  CalibrationMetrics,
  CalibrationObjective,
  CalibrationSample,
  IdentityScenario,
  IdentityType,
  ThresholdCalibrationProfile,
} from "./types";

function assertProbability(value: number, name: string): void {
  if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error(`${name} must be between 0 and 1`);
}

function assertScore(value: number): void {
  if (!Number.isFinite(value) || value < 0 || value > 100) throw new Error("calibration score must be between 0 and 100");
}

function countsAt(samples: readonly CalibrationSample[], threshold: number) {
  let tp = 0;
  let fp = 0;
  let tn = 0;
  let fn = 0;
  for (const sample of samples) {
    const positive = sample.label === "POSITIVE";
    const predicted = sample.score >= threshold;
    if (positive && predicted) tp += 1;
    else if (positive) fn += 1;
    else if (predicted) fp += 1;
    else tn += 1;
  }
  return { tp, fp, tn, fn };
}

function safeDivide(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : numerator / denominator;
}

function rocAuc(samples: readonly CalibrationSample[]): number {
  const positives = samples.filter((sample) => sample.label === "POSITIVE");
  const negatives = samples.filter((sample) => sample.label !== "POSITIVE");
  if (!positives.length || !negatives.length) return 0;
  let wins = 0;
  for (const positive of positives) {
    for (const negative of negatives) {
      if (positive.score > negative.score) wins += 1;
      else if (positive.score === negative.score) wins += 0.5;
    }
  }
  return wins / (positives.length * negatives.length);
}

function averagePrecision(samples: readonly CalibrationSample[]): number {
  const sorted = [...samples].sort((a, b) => b.score - a.score || a.sample_id.localeCompare(b.sample_id));
  const positives = sorted.filter((sample) => sample.label === "POSITIVE").length;
  if (!positives) return 0;
  let seenPositive = 0;
  let precisionSum = 0;
  sorted.forEach((sample, index) => {
    if (sample.label !== "POSITIVE") return;
    seenPositive += 1;
    precisionSum += seenPositive / (index + 1);
  });
  return precisionSum / positives;
}

export function selectCalibratedThreshold(
  samples: readonly CalibrationSample[],
  identityType: IdentityType,
  scenario: IdentityScenario,
  objective: CalibrationObjective = {},
): CalibrationMetrics {
  const filtered = samples.filter((sample) => sample.identity_type === identityType && sample.scenario === scenario);
  if (!filtered.length) throw new Error("calibration dataset is empty for identity type/scenario");
  filtered.forEach((sample) => assertScore(sample.score));
  const positiveCount = filtered.filter((sample) => sample.label === "POSITIVE").length;
  const negativeCount = filtered.filter((sample) => sample.label === "NEGATIVE").length;
  const nearMissCount = filtered.filter((sample) => sample.label === "NEAR_MISS").length;
  if (!positiveCount || !(negativeCount + nearMissCount)) {
    throw new Error("calibration requires positive and negative/near-miss samples");
  }
  const minimumPrecision = objective.minimum_precision ?? 0;
  const minimumRecall = objective.minimum_recall ?? 0;
  assertProbability(minimumPrecision, "minimum_precision");
  assertProbability(minimumRecall, "minimum_recall");

  const thresholds = [...new Set(filtered.map((sample) => sample.score))].sort((a, b) => a - b);
  let best: { threshold: number; precision: number; recall: number; f1: number; fpr: number; fnr: number } | null = null;
  for (const threshold of thresholds) {
    const { tp, fp, tn, fn } = countsAt(filtered, threshold);
    const precision = safeDivide(tp, tp + fp);
    const recall = safeDivide(tp, tp + fn);
    if (precision < minimumPrecision || recall < minimumRecall) continue;
    const f1 = safeDivide(2 * precision * recall, precision + recall);
    const fpr = safeDivide(fp, fp + tn);
    const fnr = safeDivide(fn, fn + tp);
    const candidate = { threshold, precision, recall, f1, fpr, fnr };
    if (
      !best ||
      candidate.f1 > best.f1 ||
      (candidate.f1 === best.f1 && candidate.precision > best.precision) ||
      (candidate.f1 === best.f1 && candidate.precision === best.precision && candidate.recall > best.recall) ||
      (candidate.f1 === best.f1 && candidate.precision === best.precision && candidate.recall === best.recall &&
        ((objective.prefer_higher_threshold_on_tie ?? true) ? candidate.threshold > best.threshold : candidate.threshold < best.threshold))
    ) {
      best = candidate;
    }
  }
  if (!best) throw new Error("no calibrated threshold satisfies objective");
  return {
    threshold: best.threshold,
    precision: best.precision,
    recall: best.recall,
    f1: best.f1,
    false_positive_rate: best.fpr,
    false_negative_rate: best.fnr,
    roc_auc: rocAuc(filtered),
    average_precision: averagePrecision(filtered),
    positive_count: positiveCount,
    negative_count: negativeCount,
    near_miss_count: nearMissCount,
  };
}

export interface BuildCalibrationProfileInput {
  readonly profile_id: string;
  readonly organization_id: string;
  readonly identity_type: IdentityType;
  readonly scenario: IdentityScenario;
  readonly version: string;
  readonly model_bundle_version: string;
  readonly preprocessor_version: string;
  readonly calibration_dataset_version: string;
  readonly signal_weights: Readonly<Record<string, number>>;
  readonly required_signals: readonly string[];
  readonly review_margin: number;
  readonly minimum_confidence: number;
  readonly samples: readonly CalibrationSample[];
  readonly objective?: CalibrationObjective;
}

export function buildCalibrationProfile(input: BuildCalibrationProfileInput): ThresholdCalibrationProfile {
  if (!input.required_signals.length) throw new Error("required_signals must not be empty");
  const distinctSignals = new Set(input.required_signals);
  if ((input.identity_type === "PRODUCT" || input.identity_type === "LOGO") && distinctSignals.size < 2) {
    throw new Error("PRODUCT/LOGO calibration must require multiple independent signals");
  }
  let totalWeight = 0;
  for (const [signal, weight] of Object.entries(input.signal_weights)) {
    if (!Number.isFinite(weight) || weight <= 0) throw new Error(`signal weight must be positive: ${signal}`);
    totalWeight += weight;
  }
  if (totalWeight <= 0) throw new Error("signal_weights must not be empty");
  for (const signal of input.required_signals) {
    if (!(signal in input.signal_weights)) throw new Error(`required signal has no weight: ${signal}`);
  }
  assertProbability(input.minimum_confidence, "minimum_confidence");
  if (!Number.isFinite(input.review_margin) || input.review_margin < 0 || input.review_margin > 100) {
    throw new Error("review_margin must be between 0 and 100");
  }
  const metrics = selectCalibratedThreshold(input.samples, input.identity_type, input.scenario, input.objective);
  return {
    profile_id: input.profile_id,
    organization_id: input.organization_id,
    identity_type: input.identity_type,
    scenario: input.scenario,
    version: input.version,
    status: "PUBLISHED",
    threshold: metrics.threshold,
    review_floor: Math.max(0, metrics.threshold - input.review_margin),
    minimum_confidence: input.minimum_confidence,
    signal_weights: { ...input.signal_weights },
    required_signals: [...distinctSignals].sort(),
    model_bundle_version: input.model_bundle_version,
    preprocessor_version: input.preprocessor_version,
    calibration_dataset_version: input.calibration_dataset_version,
    metrics,
  };
}
