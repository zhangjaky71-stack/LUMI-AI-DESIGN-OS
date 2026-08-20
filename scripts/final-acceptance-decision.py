#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_GATE = ROOT / "scripts" / "final-acceptance-gate.py"
PACKAGE_VALIDATOR = ROOT / "scripts" / "validate_final_acceptance_package.py"
GOVERNANCE = ROOT / "scripts" / "capture_release_branch_protection.py"
AUTHORIZATION = ROOT / "scripts" / "capture_release_authorization.py"
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"


class FinalDecisionError(RuntimeError):
    pass


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FinalDecisionError(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise FinalDecisionError(f"path escapes repository: {path}") from exc


def require_token(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise FinalDecisionError(f"required live-control token is missing: {name}")
    return value


def evaluate(
    *,
    matrix_path: Path,
    release_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    product_gate = load_module(PRODUCT_GATE, "lumi_final_product_gate")
    package_validator = load_module(PACKAGE_VALIDATOR, "lumi_final_package_validator")
    governance = load_module(GOVERNANCE, "lumi_release_branch_protection")
    authorization = load_module(AUTHORIZATION, "lumi_release_authorization")

    try:
        package_result = package_validator.validate(release_path)
    except package_validator.PackageError as exc:
        raise FinalDecisionError(f"canonical final package invalid: {exc}") from exc
    if package_result.get("status") != "PASS":
        raise FinalDecisionError("canonical final package did not PASS")

    release = product_gate.load_json(release_path)
    evidence = product_gate.load_json(evidence_path)
    matrix = product_gate.load_json(matrix_path)
    release_id = release.get("release_id")
    rc = release.get("release_candidate")
    if not isinstance(release_id, str) or not release_id:
        raise FinalDecisionError("final release_id is missing")
    if not isinstance(rc, dict) or not isinstance(rc.get("git_sha"), str):
        raise FinalDecisionError("final release candidate SHA is missing")
    rc_sha = rc["git_sha"].lower()

    runtime_dir = output_path.parent / "runtime"
    governance_path = runtime_dir / "repository-governance-live.json"
    authorization_path = runtime_dir / "release-authorization-live.json"

    governance_token = require_token("RELEASE_GOVERNANCE_TOKEN")
    governance_report = governance.capture(EXPECTED_REPOSITORY, token=governance_token)
    write_json(governance_path, governance_report)
    try:
        governance_result = governance.validate_report(
            governance_report,
            expected_repository=EXPECTED_REPOSITORY,
            expected_release_sha=rc_sha,
        )
    except governance.BranchProtectionError as exc:
        raise FinalDecisionError(f"live repository governance blocked: {exc}") from exc

    auth_spec = release.get("release_authorization")
    if not isinstance(auth_spec, dict) or not isinstance(auth_spec.get("path"), str):
        raise FinalDecisionError("release_authorization frozen path is missing")
    frozen_authorization_path = product_gate.canonical_repo_path(
        auth_spec["path"],
        allowed_prefixes=("reports/final-acceptance/",),
    )
    approval_token = require_token("RELEASE_APPROVAL_TOKEN")
    frozen_authorization = authorization._load_json(frozen_authorization_path)
    try:
        authorization_report = authorization.verify_live_authorization(
            frozen_authorization,
            token=approval_token,
        )
    except authorization.ReleaseAuthorizationError as exc:
        raise FinalDecisionError(f"live release authorization blocked: {exc}") from exc
    write_json(authorization_path, authorization_report)

    product_result = product_gate.evaluate(matrix, release, evidence, evidence_path)
    product_decision_id = product_result.pop("decision_id")

    live_controls = {
        "repository_governance": {
            "path": repo_relative(governance_path),
            "sha256": sha256(governance_path),
            "kind": governance_report.get("kind"),
            "status": governance_result.get("status"),
            "protection_profile": governance_result.get("protection_profile"),
            "release_head_sha": governance_result.get("release_head_sha"),
        },
        "release_authorization": {
            "path": repo_relative(authorization_path),
            "sha256": sha256(authorization_path),
            "kind": authorization_report.get("kind"),
            "status": authorization_report.get("status"),
            "distinct_approver_count": authorization_report.get("distinct_approver_count"),
            "actors": authorization_report.get("actors"),
        },
    }
    payload = {
        **product_result,
        "product_decision_id": product_decision_id,
        "canonical_inputs": {
            "release_manifest": {
                "path": repo_relative(release_path),
                "sha256": sha256(release_path),
            },
            "acceptance_evidence": {
                "path": repo_relative(evidence_path),
                "sha256": sha256(evidence_path),
            },
            "acceptance_matrix": {
                "path": repo_relative(matrix_path),
                "sha256": sha256(matrix_path),
            },
        },
        "live_release_controls": live_controls,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    result = {
        "decision_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24],
        **payload,
    }
    write_json(output_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate canonical NODE-73 Final Acceptance with live GitHub release controls"
    )
    parser.add_argument("--matrix", default="final/acceptance/manifest-v1.json")
    parser.add_argument("--release", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    product_gate = load_module(PRODUCT_GATE, "lumi_final_product_gate_paths")
    try:
        matrix_path = product_gate.canonical_repo_path(
            args.matrix,
            allowed_prefixes=("final/acceptance/",),
        )
        release_path = product_gate.canonical_repo_path(
            args.release,
            allowed_prefixes=("reports/final-acceptance/",),
        )
        evidence_path = product_gate.canonical_repo_path(
            args.evidence,
            allowed_prefixes=("reports/final-acceptance/",),
        )
        output_path = product_gate.canonical_repo_path(
            args.output,
            allowed_prefixes=("reports/final-acceptance/",),
        )
        result = evaluate(
            matrix_path=matrix_path,
            release_path=release_path,
            evidence_path=evidence_path,
            output_path=output_path,
        )
    except (OSError, json.JSONDecodeError, FinalDecisionError, product_gate.FinalAcceptanceError) as exc:
        raise SystemExit(f"final acceptance decision blocked: {exc}") from exc

    print(
        json.dumps(
            {
                "accepted": result["accepted"],
                "decision_id": result["decision_id"],
                "product_decision_id": result["product_decision_id"],
                "headline": result["headline"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
