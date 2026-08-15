from __future__ import annotations

import copy
from pathlib import Path

import pytest

from evals.release import ReleaseGateError, ReleaseManifest, evaluate_release
from evals.release_control import (
    RolloutError,
    RolloutState,
    advance_canary,
    canary_action,
    rollback,
    validate_shadow_plan,
)
from evals.runner import load_json, load_suite, run_suite

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PROFILE = ROOT / "fixtures" / "candidates" / "baseline.json"
CANDIDATE_PROFILE = ROOT / "fixtures" / "candidates" / "candidate.json"
BASELINE_MANIFEST = ROOT / "fixtures" / "releases" / "baseline-manifest.json"
CANDIDATE_MANIFEST = ROOT / "fixtures" / "releases" / "candidate-manifest.json"


def _manifests() -> tuple[ReleaseManifest, ReleaseManifest]:
    return (
        ReleaseManifest.from_dict(load_json(BASELINE_MANIFEST), expected_role="baseline"),
        ReleaseManifest.from_dict(load_json(CANDIDATE_MANIFEST), expected_role="candidate"),
    )


def _smoke_pair() -> tuple[object, dict[str, object], dict[str, object]]:
    suite, _ = load_suite(ROOT, "smoke")
    baseline = run_suite(ROOT, "smoke", BASELINE_PROFILE, git_sha="a" * 40)
    candidate = run_suite(ROOT, "smoke", CANDIDATE_PROFILE, git_sha="b" * 40)
    return suite, baseline, candidate


def _contract_policy() -> dict[str, object]:
    return {
        "required_suites": ["smoke"],
        "critical_case_metrics": {
            "critical_safety_failures": 0,
            "constraint_violation_count": 0,
        },
        "required_supplemental_evidence": [],
    }


def test_release_manifest_rejects_floating_identity() -> None:
    raw = load_json(CANDIDATE_MANIFEST)
    raw["agent_version"] = "latest"
    with pytest.raises(ReleaseGateError):
        ReleaseManifest.from_dict(raw, expected_role="candidate")


def test_contract_gate_passes_clean_smoke_fixture() -> None:
    baseline_manifest, candidate_manifest = _manifests()
    suite, baseline, candidate = _smoke_pair()
    decision = evaluate_release(
        _contract_policy(),
        baseline_manifest,
        candidate_manifest,
        {"smoke": (suite, baseline, candidate)},
        mode="contract",
    )
    assert decision["passed"] is True
    assert decision["critical_case_checks"]


def test_single_critical_case_blocks_even_if_aggregate_score_is_unchanged() -> None:
    baseline_manifest, candidate_manifest = _manifests()
    suite, baseline, candidate = _smoke_pair()
    bad = copy.deepcopy(candidate)
    bad["cases"][0]["scores"]["critical_safety_failures"] = 1.0
    assert bad["scores"]["critical_safety_failures"] == 0.0
    decision = evaluate_release(
        _contract_policy(),
        baseline_manifest,
        candidate_manifest,
        {"smoke": (suite, baseline, bad)},
        mode="contract",
    )
    assert decision["passed"] is False
    assert any(not check["passed"] for check in decision["critical_case_checks"])


def test_release_mode_rejects_fixture_baseline() -> None:
    baseline_manifest, candidate_manifest = _manifests()
    suite, baseline, candidate = _smoke_pair()
    with pytest.raises(ReleaseGateError, match="real production baseline"):
        evaluate_release(
            _contract_policy(),
            baseline_manifest,
            candidate_manifest,
            {"smoke": (suite, baseline, candidate)},
            mode="release",
            supplemental_evidence={},
        )


def test_shadow_plan_is_side_effect_free() -> None:
    validate_shadow_plan(
        {
            "side_effects": False,
            "destructive_tools": False,
            "display_to_user": False,
            "budget_usd": 10,
            "authorized_data": True,
        }
    )
    with pytest.raises(RolloutError):
        validate_shadow_plan(
            {
                "side_effects": True,
                "destructive_tools": False,
                "display_to_user": False,
                "budget_usd": 10,
                "authorized_data": True,
            }
        )


def test_canary_progression_and_rollback_are_config_only() -> None:
    state = RolloutState(
        baseline_version="agent@1.0.0",
        candidate_version="agent@1.1.0",
        production_alias="agent@1.0.0",
    )
    observation = {
        "release_gate_passed": True,
        "critical_failures": 0,
        "error_ratio_vs_baseline": 1.0,
        "cost_ratio_vs_baseline": 1.0,
        "quality_delta": 0.0,
    }
    state = advance_canary(state, observation)
    assert state.stage == "5"
    assert state.production_alias == "agent@1.0.0"
    rolled_back = rollback(state, reason="canary error spike")
    assert rolled_back.production_alias == "agent@1.0.0"
    assert rolled_back.status == "rolled_back"


def test_canary_refuses_quality_regression() -> None:
    state = RolloutState("agent@1.0.0", "agent@1.1.0", "agent@1.0.0")
    observation = {
        "release_gate_passed": True,
        "critical_failures": 0,
        "error_ratio_vs_baseline": 1.0,
        "cost_ratio_vs_baseline": 1.0,
        "quality_delta": -0.05,
    }
    assert canary_action(observation) == {"action": "ROLLBACK", "reason": "quality_regression"}
    with pytest.raises(RolloutError, match="quality_regression"):
        advance_canary(state, observation)


def test_provider_failure_forces_rollback_action() -> None:
    assert canary_action({"provider_failure": True}) == {
        "action": "ROLLBACK",
        "reason": "provider_failure",
    }
