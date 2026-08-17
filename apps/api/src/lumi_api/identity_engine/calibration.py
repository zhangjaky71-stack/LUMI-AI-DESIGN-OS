from __future__ import annotations

from datetime import datetime
from uuid import UUID

from .contracts import (
    CalibrationMetrics,
    CalibrationReport,
    CalibrationSample,
    IdentityType,
    SampleLabel,
    canonical_hash,
)
from .scoring import combine_signals


def _score(sample: CalibrationSample) -> float:
    score, _, _, _ = combine_signals(
        sample.identity_type,
        sample.signal_scores,
        region_quality=sample.crop_quality,
        region_confidence=1.0,
    )
    return score or 0.0


def calibrate_threshold(
    *,
    report_id: UUID,
    organization_id: UUID,
    identity_type: IdentityType,
    profile_key: str,
    version: int,
    samples: tuple[CalibrationSample, ...],
    target_precision: float,
    created_at: datetime,
) -> CalibrationReport:
    scoped = tuple(s for s in samples if s.identity_type is identity_type)
    if len(scoped) < 4:
        raise ValueError("IDENTITY_CALIBRATION_DATASET_TOO_SMALL")
    positives = [s for s in scoped if s.label is SampleLabel.POSITIVE]
    negatives = [s for s in scoped if s.label is not SampleLabel.POSITIVE]
    if not positives or not negatives:
        raise ValueError("IDENTITY_CALIBRATION_CLASSES_REQUIRED")
    scored = [(_score(s), s.label is SampleLabel.POSITIVE) for s in scoped]
    thresholds = sorted({0.0, 100.0, *(round(score, 6) for score, _ in scored)})
    candidates: list[CalibrationMetrics] = []
    for threshold in thresholds:
        tp = sum(1 for score, pos in scored if pos and score >= threshold)
        fp = sum(1 for score, pos in scored if not pos and score >= threshold)
        fn = sum(1 for score, pos in scored if pos and score < threshold)
        tn = sum(1 for score, pos in scored if not pos and score < threshold)
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        far = fp / (fp + tn) if fp + tn else 0.0
        frr = fn / (fn + tp) if fn + tp else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        candidates.append(CalibrationMetrics(
            threshold=threshold,
            precision=precision,
            recall=recall,
            false_accept_rate=far,
            false_reject_rate=frr,
            f1=f1,
            positives=len(positives),
            negatives=len(negatives),
        ))
    feasible = [m for m in candidates if m.precision >= target_precision]
    if feasible:
        selected = max(feasible, key=lambda m: (m.recall, m.f1, m.threshold))
    else:
        selected = max(candidates, key=lambda m: (m.f1, m.precision, m.threshold))
    return CalibrationReport(
        id=report_id,
        organization_id=organization_id,
        identity_type=identity_type,
        profile_key=profile_key,
        version=version,
        dataset_hash=canonical_hash([s.model_dump(mode="json") for s in scoped]),
        selected_threshold=selected.threshold,
        target_precision=target_precision,
        metrics=selected,
        sample_count=len(scoped),
        created_at=created_at,
    )
