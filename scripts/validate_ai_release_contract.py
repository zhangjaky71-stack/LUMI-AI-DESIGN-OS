#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from evals.live import AUTHORIZATION_ONLY_MODE, live_preflight
from evals.release import ReleaseGateError, ReleaseManifest, evaluate_release
from evals.release_control import RolloutState, advance_canary, rollback, validate_shadow_plan
from evals.runner import load_json, load_suite, run_suite

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
CLI = EVALS / "cli.py"
WORKFLOW = ROOT / ".github" / "workflows" / "ai-regression-release-gate.yml"

FIXTURE_PATHS = {
    "smoke": (
        EVALS / "fixtures" / "candidates" / "baseline.json",
        EVALS / "fixtures" / "candidates" / "candidate.json",
    ),
    "auto-repair": (
        EVALS / "fixtures" / "auto-repair" / "baseline.json",
        EVALS / "fixtures" / "auto-repair" / "candidate.json",
    ),
    "visual-critic": (
        EVALS / "fixtures" / "visual-critic" / "baseline.json",
        EVALS / "fixtures" / "visual-critic" / "candidate.json",
    ),
}

LIVE_ENV_KEYS = [
    "LUMI_LIVE_EVAL_ENABLED",
    "LUMI_LIVE_EVAL_PREFLIGHT_MODE",
    "LUMI_LIVE_EVAL_API_KEY",
    "LUMI_LIVE_EVAL_BUDGET_USD",
    "LUMI_LIVE_EVAL_MAX_BUDGET_USD",
    "LUMI_LIVE_EVAL_SUITE_ACK",
    "LUMI_LIVE_EVAL_SIDE_EFFECT_MODE",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"AI release contract invalid: {message}")


def build_fixture_pairs(required_suites: list[str]) -> dict[str, tuple[Any, dict[str, Any], dict[str, Any]]]:
    pairs: dict[str, tuple[Any, dict[str, Any], dict[str, Any]]] = {}
    for suite_name in required_suites:
        paths = FIXTURE_PATHS.get(suite_name)
        require(paths is not None, f"no contract fixture mapping for {suite_name}")
        suite, cases = load_suite(EVALS, suite_name)
        require(suite.version == "1.0.0", f"{suite_name} suite version must be pinned")
        require(bool(cases), f"{suite_name} must contain executable cases")
        baseline_path, candidate_path = paths
        pairs[suite_name] = (
            suite,
            run_suite(EVALS, suite_name, baseline_path, git_sha="a" * 40),
            run_suite(EVALS, suite_name, candidate_path, git_sha="b" * 40),
        )
    return pairs


def validate_secretless_live_preflight() -> dict[str, Any]:
    saved = {key: os.environ.get(key) for key in LIVE_ENV_KEYS}
    try:
        for key in LIVE_ENV_KEYS:
            os.environ.pop(key, None)
        require(live_preflight("smoke")["status"] == "SKIPPED", "live eval must be disabled by default")

        os.environ["LUMI_LIVE_EVAL_ENABLED"] = "1"
        os.environ["LUMI_LIVE_EVAL_PREFLIGHT_MODE"] = AUTHORIZATION_ONLY_MODE
        os.environ["LUMI_LIVE_EVAL_BUDGET_USD"] = "5"
        os.environ["LUMI_LIVE_EVAL_MAX_BUDGET_USD"] = "25"
        os.environ["LUMI_LIVE_EVAL_SUITE_ACK"] = "smoke"
        os.environ["LUMI_LIVE_EVAL_SIDE_EFFECT_MODE"] = "none"
        os.environ.pop("LUMI_LIVE_EVAL_API_KEY", None)

        ready = live_preflight("smoke")
        require(ready.get("status") == "READY", "clean authorization-only preflight must be READY")
        require(ready.get("preflight_mode") == AUTHORIZATION_ONLY_MODE, "preflight mode drift")
        require(ready.get("credential_check") == "NOT_PERFORMED", "preflight must not validate provider credentials")
        require(ready.get("network_execution") is False, "preflight must not execute provider network calls")
        require(ready.get("side_effect_mode") == "none", "preflight side-effect mode must remain none")

        os.environ["LUMI_LIVE_EVAL_API_KEY"] = "forbidden-in-preflight"
        require(
            live_preflight("smoke").get("status") == "SKIPPED",
            "authorization preflight must reject injected provider credentials",
        )
        os.environ.pop("LUMI_LIVE_EVAL_API_KEY", None)

        os.environ["LUMI_LIVE_EVAL_PREFLIGHT_MODE"] = "provider-execution"
        require(
            live_preflight("smoke").get("status") == "SKIPPED",
            "unknown/provider-execution preflight mode must block",
        )
        os.environ["LUMI_LIVE_EVAL_PREFLIGHT_MODE"] = AUTHORIZATION_ONLY_MODE

        os.environ["LUMI_LIVE_EVAL_BUDGET_USD"] = "25.01"
        require(
            live_preflight("smoke").get("status") == "SKIPPED",
            "preflight budget above configured maximum must block",
        )
    finally:
        for key in LIVE_ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value

    cli_source = CLI.read_text(encoding="utf-8")
    workflow_source = WORKFLOW.read_text(encoding="utf-8")
    require(
        'return 0 if result.get("status") == "READY" else 2' in cli_source,
        "live CLI must fail closed when authorization preflight is not READY",
    )
    require(
        "LUMI_LIVE_EVAL_API_KEY" not in workflow_source,
        "AI Regression workflow must not inject Provider credentials into preflight",
    )
    require(
        'LUMI_LIVE_EVAL_PREFLIGHT_MODE: "authorization-only"' in workflow_source,
        "AI Regression workflow must explicitly bind authorization-only mode",
    )
    require(
        "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/release-closure-p0'" in workflow_source,
        "authorization preflight must be manual release-ref only",
    )
    require(
        'ref: ${{ github.sha }}' in workflow_source and "persist-credentials: false" in workflow_source,
        "authorization preflight must execute exact dispatch SHA without persisted credentials",
    )
    return ready


def main() -> int:
    policy = load_json(EVALS / "release" / "policy-v1.json")
    require(policy.get("schema_version") == 1, "policy schema_version must be 1")
    required_suites_raw = policy.get("required_suites")
    require(
        isinstance(required_suites_raw, list)
        and bool(required_suites_raw)
        and all(isinstance(item, str) for item in required_suites_raw),
        "required_suites missing",
    )
    required_suites = list(required_suites_raw)

    baseline_manifest = ReleaseManifest.from_dict(
        load_json(EVALS / "fixtures" / "releases" / "baseline-manifest.json"),
        expected_role="baseline",
    )
    candidate_manifest = ReleaseManifest.from_dict(
        load_json(EVALS / "fixtures" / "releases" / "candidate-manifest.json"),
        expected_role="candidate",
    )
    require(set(baseline_manifest.suite_versions) == set(required_suites), "baseline manifest suite set must equal release policy")
    require(set(candidate_manifest.suite_versions) == set(required_suites), "candidate manifest suite set must equal release policy")

    pairs = build_fixture_pairs(required_suites)
    clean = evaluate_release(
        policy,
        baseline_manifest,
        candidate_manifest,
        pairs,
        mode="contract",
    )
    require(clean["passed"] is True, "clean fixtures for all blocking suites must pass contract mode")
    require(len(clean["suite_results"]) == len(required_suites), "every blocking suite must contribute a gate result")

    bad_pairs = copy.deepcopy(pairs)
    smoke_suite, smoke_baseline, smoke_candidate = bad_pairs["smoke"]
    smoke_candidate["cases"][0]["scores"]["critical_safety_failures"] = 1.0
    require(smoke_candidate["scores"]["critical_safety_failures"] == 0.0, "drill must leave aggregate unchanged")
    bad_pairs["smoke"] = (smoke_suite, smoke_baseline, smoke_candidate)
    blocked = evaluate_release(
        policy,
        baseline_manifest,
        candidate_manifest,
        bad_pairs,
        mode="contract",
    )
    require(blocked["passed"] is False, "single critical case must block full release")

    try:
        evaluate_release(
            policy,
            baseline_manifest,
            candidate_manifest,
            pairs,
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

    live_ready = validate_secretless_live_preflight()

    output = {
        "status": "PASS",
        "policy_id": policy.get("policy_id"),
        "executable_suites": required_suites,
        "clean_contract_decision": clean["decision_id"],
        "blocking_suite_count": len(clean["suite_results"]),
        "bad_candidate_blocked": True,
        "fixture_release_mode_blocked": True,
        "per_suite_profiles_pinned": True,
        "shadow_side_effect_free": True,
        "rollback_contract": True,
        "live_provider_default": "SKIPPED",
        "live_provider_preflight": "SECRETLESS_AUTHORIZATION_ONLY",
        "live_provider_credential_check": live_ready["credential_check"],
        "live_provider_network_execution": live_ready["network_execution"],
        "provider_secret_in_preflight_blocked": True,
        "preflight_non_ready_exit_nonzero": True,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
