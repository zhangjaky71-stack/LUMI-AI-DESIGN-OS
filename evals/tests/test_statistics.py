from __future__ import annotations

from evals.statistics import compare_success_rates, summarize_samples, wilson_interval


def test_sample_summary_records_uncertainty() -> None:
    summary = summarize_samples([1.0, 2.0, 3.0, 4.0])
    assert summary["n"] == 4
    assert summary["confidence_method"] == "normal_approx_95"
    assert summary["ci95_low"] is not None
    assert summary["ci95_high"] is not None


def test_wilson_interval_is_bounded() -> None:
    interval = wilson_interval(18, 20)
    assert 0 <= interval["ci95_low"] <= interval["rate"] <= interval["ci95_high"] <= 1
    assert interval["confidence_method"] == "wilson_95"


def test_comparison_never_declares_significance_implicitly() -> None:
    comparison = compare_success_rates(18, 20, 19, 20)
    assert comparison["delta"] > 0
    assert comparison["claim_significant_improvement"] is False
