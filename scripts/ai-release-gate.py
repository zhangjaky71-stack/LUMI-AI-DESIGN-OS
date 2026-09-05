#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evals.release import ReleaseManifest, evaluate_release
from evals.runner import load_json, load_suite

ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals"
DEFAULT_POLICY = EVAL_ROOT / "release" / "policy-v1.json"


def parse_named_paths(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"expected SUITE=PATH, got {value!r}")
        suite, raw_path = value.split("=", 1)
        if not suite or not raw_path or suite in result:
            raise SystemExit(f"invalid or duplicate suite path: {value!r}")
        result[suite] = Path(raw_path)
    return result


def extract_run(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    run = payload.get("run", payload)
    if not isinstance(run, dict):
        raise SystemExit(f"{path} does not contain a run object")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description="LUMI AI production release gate")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--baseline-manifest", required=True)
    parser.add_argument("--candidate-manifest", required=True)
    parser.add_argument("--baseline-run", action="append", default=[], metavar="SUITE=PATH")
    parser.add_argument("--candidate-run", action="append", default=[], metavar="SUITE=PATH")
    parser.add_argument("--supplemental-evidence")
    parser.add_argument("--mode", choices=["contract", "release"], default="release")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    policy = load_json(Path(args.policy))
    baseline_manifest = ReleaseManifest.from_dict(
        load_json(Path(args.baseline_manifest)), expected_role="baseline"
    )
    candidate_manifest = ReleaseManifest.from_dict(
        load_json(Path(args.candidate_manifest)), expected_role="candidate"
    )
    baseline_paths = parse_named_paths(args.baseline_run)
    candidate_paths = parse_named_paths(args.candidate_run)
    required = policy.get("required_suites", [])
    if not isinstance(required, list):
        raise SystemExit("policy.required_suites must be an array")

    pairs = {}
    for suite_name in required:
        if suite_name not in baseline_paths or suite_name not in candidate_paths:
            raise SystemExit(f"missing baseline/candidate run for required suite {suite_name}")
        suite, _ = load_suite(EVAL_ROOT, suite_name)
        pairs[suite_name] = (
            suite,
            extract_run(baseline_paths[suite_name]),
            extract_run(candidate_paths[suite_name]),
        )

    supplemental = None
    if args.supplemental_evidence:
        supplemental = load_json(Path(args.supplemental_evidence))

    decision = evaluate_release(
        policy,
        baseline_manifest,
        candidate_manifest,
        pairs,
        mode=args.mode,
        supplemental_evidence=supplemental,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if decision["passed"] else "BLOCK", "decision_id": decision["decision_id"], "output": str(output)}, sort_keys=True))
    return 0 if decision["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
