#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
GOVERNANCE_VALIDATOR = ROOT / "scripts" / "capture_release_branch_protection.py"
UPSTREAM = {
    "security",
    "recovery",
    "performance",
    "ai_regression",
    "staging_acceptance",
    "production_deployment",
}
APPROVAL_KEYS = {"product", "engineering", "security", "operations", "release_owner"}
HANDOFF_KEYS = {
    "on_call_owner",
    "support_owner",
    "incident_commander_rotation",
    "first_day_watch_owner",
    "quality_cost_review_owner",
    "security_dependency_review_owner",
    "dr_drill_owner",
    "capacity_review_owner",
}
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"


class PackageError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PackageError(f"{path} must contain a JSON object")
    return payload


def load_governance_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_release_branch_protection", GOVERNANCE_VALIDATOR)
    if spec is None or spec.loader is None:
        raise PackageError("unable to load canonical release branch protection validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo_file(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw or raw.upper() == "PENDING":
        raise PackageError("frozen path missing/PENDING")
    path = (ROOT / raw).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise PackageError(f"path escapes repository: {raw}") from exc
    if not path.is_file():
        raise PackageError(f"frozen file missing: {raw}")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_ref(ref: Any, *, label: str) -> Path:
    if not isinstance(ref, dict):
        raise PackageError(f"{label} must be an object")
    path = repo_file(ref.get("path"))
    expected = ref.get("sha256")
    if not isinstance(expected, str) or digest(path) != expected.lower():
        raise PackageError(f"{label} SHA-256 mismatch")
    return path


def rc(payload: dict[str, Any]) -> tuple[Any, Any, Any]:
    value = payload.get("release_candidate")
    if not isinstance(value, dict):
        return None, None, None
    return value.get("git_sha"), value.get("version"), value.get("migration_head")


def validate_repository_governance(
    release: dict[str, Any],
    *,
    expected_release_sha: str,
) -> Path:
    path = verify_ref(release.get("repository_governance"), label="repository_governance")
    report = load(path)
    validator = load_governance_validator()
    try:
        validator.validate_report(
            report,
            expected_repository=EXPECTED_REPOSITORY,
            expected_release_sha=expected_release_sha,
        )
    except validator.BranchProtectionError as exc:
        raise PackageError(f"repository governance invalid: {exc}") from exc
    return path


def validate(release_path: Path) -> dict[str, Any]:
    release = load(release_path)
    release_id = release.get("release_id")
    expected_rc = rc(release)
    if release.get("schema_version") != 1 or not isinstance(release_id, str) or not release_id:
        raise PackageError("release package schema/release_id invalid")
    if any(value is None or value == "PENDING" for value in expected_rc):
        raise PackageError("release package RC identity incomplete")
    release_sha = expected_rc[0]
    if not isinstance(release_sha, str) or not SHA40.fullmatch(release_sha.lower()):
        raise PackageError("release package RC git_sha must be exact SHA40")

    assembly = release.get("assembly")
    if not isinstance(assembly, dict) or assembly.get("schema_version") != 1:
        raise PackageError("release package lacks canonical assembly metadata")
    if assembly.get("assembler") != "scripts/final-acceptance-assembler.py":
        raise PackageError("release package was not produced by the canonical assembler")
    matrix_path = verify_ref(assembly.get("matrix"), label="assembly.matrix")
    scenario_path = verify_ref(assembly.get("scenario_results"), label="assembly.scenario_results")
    if matrix_path.resolve() != (ROOT / "final/acceptance/manifest-v1.json").resolve():
        raise PackageError("release package does not use canonical final acceptance matrix")

    governance_path = validate_repository_governance(
        release,
        expected_release_sha=release_sha,
    )

    authorization_path = verify_ref(release.get("release_authorization"), label="release_authorization")
    authorization = load(authorization_path)
    if authorization.get("schema_version") != 1 or authorization.get("release_id") != release_id:
        raise PackageError("release authorization schema/release_id mismatch")
    if rc(authorization) != expected_rc:
        raise PackageError("release authorization RC identity mismatch")
    approvals = authorization.get("approvals")
    handoff = authorization.get("operational_handoff")
    if not isinstance(approvals, dict) or set(approvals) != APPROVAL_KEYS or any(v != "APPROVED" for v in approvals.values()):
        raise PackageError("release authorization approvals are incomplete")
    if release.get("approvals") != approvals:
        raise PackageError("release approvals were modified after authorization")
    if not isinstance(handoff, dict) or set(handoff) != HANDOFF_KEYS or any(not isinstance(v, str) or not v or v.upper() == "PENDING" for v in handoff.values()):
        raise PackageError("release authorization operational handoff is incomplete")
    if release.get("operational_handoff") != handoff:
        raise PackageError("release operational handoff was modified after authorization")

    upstream = release.get("upstream_gates")
    if not isinstance(upstream, dict) or set(upstream) != UPSTREAM:
        raise PackageError(f"release upstream gate set must equal {sorted(UPSTREAM)}")
    upstream_decisions: dict[str, str] = {}
    for name in sorted(UPSTREAM):
        path = verify_ref(upstream[name], label=f"upstream.{name}")
        decision = load(path)
        if decision.get("passed") is not True or not isinstance(decision.get("decision_id"), str) or not decision["decision_id"]:
            raise PackageError(f"upstream {name} is not a concrete passed=true decision")
        if rc(decision) != expected_rc:
            raise PackageError(f"upstream {name} RC identity mismatch")
        refs = decision.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise PackageError(f"upstream {name} lacks frozen evidence_refs")
        for index, ref in enumerate(refs):
            verify_ref(ref, label=f"upstream.{name}.evidence_refs[{index}]")
        upstream_decisions[name] = str(decision["decision_id"])

    evidence_path = verify_ref(release.get("acceptance_evidence"), label="acceptance_evidence")
    evidence = load(evidence_path)
    if evidence.get("release_id") != release_id or rc(evidence) != expected_rc:
        raise PackageError("acceptance evidence release/RC identity mismatch")
    assembly_inputs = evidence.get("assembly_inputs")
    if not isinstance(assembly_inputs, dict):
        raise PackageError("acceptance evidence lacks assembly_inputs")
    scenario_input = verify_ref(assembly_inputs.get("scenario_results"), label="acceptance_evidence.scenario_results")
    if scenario_input.resolve() != scenario_path.resolve():
        raise PackageError("acceptance evidence scenario-results source mismatch")

    return {
        "status": "PASS",
        "release_id": release_id,
        "release_candidate": release.get("release_candidate"),
        "upstream_decisions": upstream_decisions,
        "repository_governance_sha256": digest(governance_path),
        "authorization_sha256": digest(authorization_path),
        "scenario_results_sha256": digest(scenario_path),
        "acceptance_evidence_sha256": digest(evidence_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a canonical NODE-73 final acceptance package")
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    try:
        release_path = repo_file(args.release)
        result = validate(release_path)
    except (OSError, json.JSONDecodeError, PackageError) as exc:
        raise SystemExit(f"final acceptance package invalid: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
