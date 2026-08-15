from __future__ import annotations

import math
import statistics
from typing import Iterable


class StatisticsError(ValueError):
    """Raised when statistical evidence is malformed or too small to summarize."""


def percentile(values: list[float], p: float) -> float:
    if not values:
        raise StatisticsError("cannot compute percentile of an empty sample")
    if not 0 <= p <= 1:
        raise StatisticsError("percentile must be within 0..1")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
    return ordered[index]


def summarize_samples(values: Iterable[float]) -> dict[str, float | int | str | None]:
    sample = [float(value) for value in values]
    if not sample:
        raise StatisticsError("sample must contain at least one value")
    if any(not math.isfinite(value) for value in sample):
        raise StatisticsError("sample values must be finite")
    n = len(sample)
    mean = statistics.fmean(sample)
    if n >= 2:
        stdev = statistics.stdev(sample)
        standard_error = stdev / math.sqrt(n)
        ci_low = mean - 1.96 * standard_error
        ci_high = mean + 1.96 * standard_error
        confidence_method: str | None = "normal_approx_95"
    else:
        stdev = 0.0
        standard_error = 0.0
        ci_low = None
        ci_high = None
        confidence_method = None
    return {
        "n": n,
        "mean": mean,
        "min": min(sample),
        "max": max(sample),
        "p50": percentile(sample, 0.50),
        "p95": percentile(sample, 0.95),
        "stdev": stdev,
        "standard_error": standard_error,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "confidence_method": confidence_method,
    }


def wilson_interval(successes: int, total: int, *, z: float = 1.96) -> dict[str, float | int | str]:
    if total <= 0 or successes < 0 or successes > total:
        raise StatisticsError("successes/total are invalid")
    p = successes / total
    denominator = 1 + (z * z) / total
    center = (p + (z * z) / (2 * total)) / denominator
    margin = (z / denominator) * math.sqrt((p * (1 - p) / total) + (z * z) / (4 * total * total))
    return {
        "n": total,
        "successes": successes,
        "rate": p,
        "ci95_low": max(0.0, center - margin),
        "ci95_high": min(1.0, center + margin),
        "confidence_method": "wilson_95",
    }


def compare_success_rates(
    baseline_successes: int,
    baseline_total: int,
    candidate_successes: int,
    candidate_total: int,
) -> dict[str, object]:
    baseline = wilson_interval(baseline_successes, baseline_total)
    candidate = wilson_interval(candidate_successes, candidate_total)
    return {
        "baseline": baseline,
        "candidate": candidate,
        "delta": float(candidate["rate"]) - float(baseline["rate"]),
        "claim_significant_improvement": False,
        "note": "NODE-70 records uncertainty; significance claims require a predeclared test and sufficient sample size.",
    }
