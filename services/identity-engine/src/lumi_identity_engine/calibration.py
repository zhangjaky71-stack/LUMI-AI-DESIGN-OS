from __future__ import annotations

from collections.abc import Iterable

from .model import (
    CalibrationMetrics,
    CalibrationSample,
    IdentityScenario,
    IdentityType,
    ThresholdCalibrationProfile,
)


def _divide(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _roc_auc(samples: tuple[CalibrationSample, ...]) -> float:
    positives = tuple(row for row in samples if row.label == "POSITIVE")
    negatives = tuple(row for row in samples if row.label != "POSITIVE")
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive.score > negative.score:
                wins += 1.0
            elif positive.score == negative.score:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def _average_precision(samples: tuple[CalibrationSample, ...]) -> float:
    ordered = sorted(samples, key=lambda row: (-row.score, row.sample_id))
    positive_count = sum(row.label == "POSITIVE" for row in ordered)
    if positive_count == 0:
        return 0.0
    seen_positive = 0
    precision_sum = 0.0
    for index, row in enumerate(ordered, start=1):
        if row.label == "POSITIVE":
            seen_positive += 1
            precision_sum += seen_positive / index
    return precision_sum / positive_count


def select_calibrated_threshold(
    samples: Iterable[CalibrationSample],
    identity_type: IdentityType,
    scenario: IdentityScenario,
    *,
    minimum_precision: float = 0.0,
    minimum_recall: float = 0.0,
) -> CalibrationMetrics:
    rows = tuple(
        row for row in samples if row.identity_type == identity_type and row.scenario == scenario
    )
    if not rows:
        raise ValueError("calibration dataset is empty for identity type/scenario")
    if not 0 <= minimum_precision <= 1 or not 0 <= minimum_recall <= 1:
        raise ValueError("calibration objective must be between 0 and 1")
    for row in rows:
        if not 0 <= row.score <= 100:
            raise ValueError("calibration score must be between 0 and 100")
    positive_count = sum(row.label == "POSITIVE" for row in rows)
    negative_count = sum(row.label == "NEGATIVE" for row in rows)
    near_miss_count = sum(row.label == "NEAR_MISS" for row in rows)
    if positive_count == 0 or negative_count + near_miss_count == 0:
        raise ValueError("calibration requires positive and negative/near-miss samples")

    best: tuple[float, float, float, float, float, float] | None = None
    for threshold in sorted({row.score for row in rows}):
        tp = fp = tn = fn = 0
        for row in rows:
            expected = row.label == "POSITIVE"
            predicted = row.score >= threshold
            if expected and predicted:
                tp += 1
            elif expected:
                fn += 1
            elif predicted:
                fp += 1
            else:
                tn += 1
        precision = _divide(tp, tp + fp)
        recall = _divide(tp, tp + fn)
        if precision < minimum_precision or recall < minimum_recall:
            continue
        f1 = _divide(2 * precision * recall, precision + recall)
        fpr = _divide(fp, fp + tn)
        fnr = _divide(fn, fn + tp)
        candidate = (f1, precision, recall, threshold, fpr, fnr)
        if best is None or candidate[:4] > best[:4]:
            best = candidate
    if best is None:
        raise ValueError("no calibrated threshold satisfies objective")
    f1, precision, recall, threshold, fpr, fnr = best
    return CalibrationMetrics(
        threshold=threshold,
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        roc_auc=_roc_auc(rows),
        average_precision=_average_precision(rows),
        positive_count=positive_count,
        negative_count=negative_count,
        near_miss_count=near_miss_count,
    )


def build_calibration_profile(
    *,
    profile_id: str,
    organization_id: str,
    identity_type: IdentityType,
    scenario: IdentityScenario,
    version: str,
    model_bundle_version: str,
    preprocessor_version: str,
    calibration_dataset_version: str,
    signal_weights: dict[str, float],
    required_signals: tuple[str, ...],
    review_margin: float,
    minimum_confidence: float,
    samples: Iterable[CalibrationSample],
    minimum_precision: float = 0.0,
    minimum_recall: float = 0.0,
) -> ThresholdCalibrationProfile:
    distinct_signals = tuple(sorted(set(required_signals)))
    if not distinct_signals:
        raise ValueError("required_signals must not be empty")
    if identity_type in {"PRODUCT", "LOGO"} and len(distinct_signals) < 2:
        raise ValueError("PRODUCT/LOGO calibration must require multiple independent signals")
    if not 0 <= minimum_confidence <= 1:
        raise ValueError("minimum_confidence must be between 0 and 1")
    if not 0 <= review_margin <= 100:
        raise ValueError("review_margin must be between 0 and 100")
    for signal in distinct_signals:
        if signal not in signal_weights:
            raise ValueError(f"required signal has no weight: {signal}")
    if not signal_weights or any(weight <= 0 for weight in signal_weights.values()):
        raise ValueError("signal weights must be positive")
    metrics = select_calibrated_threshold(
        samples,
        identity_type,
        scenario,
        minimum_precision=minimum_precision,
        minimum_recall=minimum_recall,
    )
    return ThresholdCalibrationProfile(
        profile_id=profile_id,
        organization_id=organization_id,
        identity_type=identity_type,
        scenario=scenario,
        version=version,
        threshold=metrics.threshold,
        review_floor=max(0.0, metrics.threshold - review_margin),
        minimum_confidence=minimum_confidence,
        signal_weights=dict(signal_weights),
        required_signals=distinct_signals,
        model_bundle_version=model_bundle_version,
        preprocessor_version=preprocessor_version,
        calibration_dataset_version=calibration_dataset_version,
        metrics=metrics,
    )
