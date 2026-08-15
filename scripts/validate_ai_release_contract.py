#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from evals.live import live_preflight
from evals.release import ReleaseGateError, ReleaseManifest, evaluate_release
from evals.release_control import RolloutState, advance_canary, rollback, validate_shadow_plan
from evals.runner import load_json, load_suite, run_suite

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"AI release contract invalid: {message}")


def main() -> int:
    policy = load_json(EVALS / "release" / "policy-v1.json")
    require(policy.get("schema_version") == 1, "policy schema_version must be 1")
    required_suites = policy.get("required_suites")
    require(isinstance(required_suites, list) and bool(required_suites), "required_suites missing")
    for suite_name in required_suites:
        suite, cases = load_suite(EVALS, suite_name)
        require(suite.version == "1.0.0", f"{suite_name} suite version must be pinned")
        require(bool(cases), f"{suite_name} must contain executable cases")

    baseline_manifest = ReleaseManifest.from_dict(
        load_json(EVALS / "fixtures" / "releases" / "baseline-manifest.json"),
        expected_role="baseline",
    )
    candidate_manifest = ReleaseManifest.from_dict(
        load_json(EVALS / "fixtures" / "releases" / "candidate-manifest.json"),
        expected_role="candidate",
    )
    suite, _ = load_suite(EVALS, "smoke")
    baseline = run_suite(
        EVALS,
        "smoke",
        EVALS / "fixtures" / "candidates" / "baseline.json",
        git_sha="a" * 40,
    )
    candidate = run_suite(
        EVALS,
        "smoke",
        EVALS / "fixtures" / "candidates" / "candidate.json",
        git_sha="b" * 40,
    )
    contract_policy = {
        "required_suites": ["smoke"],
        "critical_case_metrics": {
            "critical_safety_failures": 0,
            "constraint_violation_count": 0,
        },
        "required_supplemental_evidence": [],
    }
    clean = evaluate_release(
        contract_policy,
        baseline_manifest,
        candidate_manifest,
        {"smoke": (suite, baseline, candidate)},
        mode="contract",
    )
    require(clean["passed"] is True, "clean fixture candidate must pass contract mode")

    bad = copy.deepcopy(candidate)
    bad["cases"][0]["scores"]["critical_safety_failures"] = 1.0
    blocked = evaluate_release(
        contract_policy,
        baseline_manifest,
        candidate_manifest,
        {"smoke": (suite, baseline, bad)},
        mode="contract",
    )
    require(blocked["passed"] is False, "single critical case must block release")

    try:
        evaluate_release(
            contract_policy,
            baseline_manifest,
            candidate_manifest,
            {"smoke": (suite, baseline, candidate)},
            mode="release",
            supplemental_evidence={},
        )
    except ReleaseGateError:
        pass
    else:
        raise SystemExit("AI release contract invalid: fixture evidence must never pass release mode")

    validate_shadow_plan(
        {
            "side_effects": False,
            "destructive_tools": False,
            "display_to_user": False,
            "budget_usd": 10,
            "authorized_data": True,
        }
    )
    state = RolloutState("agent@1.0.0", "agent@1.1.0", "agent@1.0.0")
    state = advance_canary(
        state,
        {
            "release_gate_passed": True,
            "critical_failures": 0,
            "error_ratio_vs_baseline": 1.0,
            "cost_ratio_vs_baseline": 1.0,
            "quality_delta": 0.0,
        },
    )
    require(state.stage == "5", "canary must progress internal -> 5")
    require(rollback(state, reason="drill").production_alias == "agent@1.0.0", "rollback must restore baseline alias")

    saved = {key: os.environ.get(key) for key in [
        "LUMI_LIVE_EVAL_ENABLED",
        "LUMI_LIVE_EVAL_API_KEY",
        "LUMI_LIVE_EVAL_BUDGET_USD",
        "LUMI_LIVE_EVAL_SUITE_ACK",
        "LUMI_LIVE_EVAL_SIDE_EFFECT_MODE",
    ]}
    try:
        for key in saved:
            os.environ.pop(key, None)
        require(live_preflight("smoke")["status"] == "SKIPPED", "live eval must be disabled by default")
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value

    output = {
        "status": "PASS",
        "policy_id": policy.get("policy_id"),
        "executable_suites": required_suites,
        "clean_contract_decision": clean["decision_id"],
        "bad_candidate_blocked": True,
        "fixture_release_mode_blocked": True,
        "shadow_side_effect_free": True,
        "rollback_contract": True,
        "live_provider_default": "SKIPPED",
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
