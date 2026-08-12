from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.gate import GateError, compare_runs
from evals.graders import GraderError, grade_case
from evals.live import live_preflight
from evals.models import EvalCase, SchemaError
from evals.reporting import canonical_json, render_markdown
from evals.runner import aggregate, load_suite, run_suite


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "fixtures" / "candidates" / "baseline.json"
CANDIDATE = ROOT / "fixtures" / "candidates" / "candidate.json"


def test_smoke_dataset_has_at_least_twenty_versioned_cases() -> None:
    suite, cases = load_suite(ROOT, "smoke")
    assert suite.version == "1.0.0"
    assert len(cases) >= 20
    assert all(case.version >= 1 for case in cases)


def test_invalid_case_schema_is_rejected() -> None:
    with pytest.raises(SchemaError):
        EvalCase.from_dict({"id": "bad"})


def test_grader_exception_is_not_silently_converted_to_zero() -> None:
    case = EvalCase.from_dict(
        {
            "id": "grader-error",
            "suite": "smoke",
            "version": 1,
            "input": {},
            "expected": {},
            "metrics": ["task_success"],
            "grader": {
                "checks": [{"path": "value", "op": "not-a-real-op", "metric": "task_success"}]
            },
        }
    )
    with pytest.raises(GraderError):
        grade_case(case, {"value": 1})


def test_baseline_candidate_pairing_requires_same_suite() -> None:
    suite, _ = load_suite(ROOT, "smoke")
    baseline = run_suite(ROOT, "smoke", BASELINE, git_sha="test")
    candidate = run_suite(ROOT, "smoke", CANDIDATE, git_sha="test")
    candidate["suite"] = "other"
    with pytest.raises(GateError):
        compare_runs(suite, baseline, candidate)


def test_cost_aggregation_is_deterministic() -> None:
    suite, _ = load_suite(ROOT, "smoke")
    values = [1.0, 2.0, 3.0, 100.0]
    assert aggregate(values, suite.metrics["cost_usd"]) == 100.0


def test_report_rendering_is_reproducible() -> None:
    run = run_suite(ROOT, "smoke", CANDIDATE, git_sha="stable-sha")
    first = canonical_json({"run": run})
    second = canonical_json({"run": run})
    assert first == second
    assert render_markdown(run) == render_markdown(run)


def test_live_eval_without_enable_flag_is_explicitly_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LUMI_LIVE_EVAL_ENABLED", raising=False)
    monkeypatch.delenv("LUMI_LIVE_EVAL_API_KEY", raising=False)
    result = live_preflight("image")
    assert result["status"] == "SKIPPED"
    assert "not 1" in result["reason"]


def test_live_eval_without_key_is_explicitly_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUMI_LIVE_EVAL_ENABLED", "1")
    monkeypatch.delenv("LUMI_LIVE_EVAL_API_KEY", raising=False)
    monkeypatch.setenv("LUMI_LIVE_EVAL_BUDGET_USD", "1")
    result = live_preflight("image")
    assert result["status"] == "SKIPPED"
    assert "API_KEY" in result["reason"]


def test_clean_smoke_candidate_passes_release_gate() -> None:
    suite, _ = load_suite(ROOT, "smoke")
    baseline = run_suite(ROOT, "smoke", BASELINE, git_sha="test")
    candidate = run_suite(ROOT, "smoke", CANDIDATE, git_sha="test")
    gate = compare_runs(suite, baseline, candidate)
    assert gate["passed"] is True
    assert baseline["scores"]["task_success"] == 1.0
    assert candidate["scores"]["constraint_violation_count"] == 0.0


def test_release_gate_rejects_primary_metric_regression() -> None:
    suite, _ = load_suite(ROOT, "smoke")
    baseline = run_suite(ROOT, "smoke", BASELINE, git_sha="test")
    candidate = json.loads(json.dumps(run_suite(ROOT, "smoke", CANDIDATE, git_sha="test")))
    candidate["scores"]["task_success"] = 0.5
    gate = compare_runs(suite, baseline, candidate)
    assert gate["passed"] is False
    assert any(not check["passed"] for check in gate["checks"])
