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
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GOVERNANCE_POLICY_VALIDATOR = ROOT / "scripts" / "validate_release_governance_policy.py"
AUTHORIZATION_V2 = ROOT / "scripts" / "capture_release_authorization_v2.py"
FINAL_STATUSES = {"PASS", "FAIL", "BLOCKED_EXTERNAL", "DEFERRED_NON_CRITICAL"}
UPSTREAM_GATES = (
    "security",
    "recovery",
    "performance",
    "ai_regression",
    "staging_acceptance",
    "production_deployment",
)
APPROVAL_KEYS = ("product", "engineering", "security", "operations", "release_owner")


class AssemblyV2Error(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssemblyV2Error(f"{path} must contain a JSON object")
    return payload


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssemblyV2Error(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def repo_file(raw: str, *, prefixes: tuple[str, ...]) -> Path:
    path = (ROOT / raw).resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise AssemblyV2Error(f"path escapes repository: {raw}") from exc
    if not any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in prefixes):
        raise AssemblyV2Error(f"path outside allowed roots: {raw}")
    if not path.is_file():
        raise AssemblyV2Error(f"required file missing: {raw}")
    return path


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise AssemblyV2Error(f"path escapes repository: {path}") from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen(path: Path) -> dict[str, str]:
    return {"path": repo_relative(path), "sha256": sha256(path)}


def rc_identity(payload: dict[str, Any]) -> tuple[Any, Any, Any]:
    rc = payload.get("release_candidate")
    if not isinstance(rc, dict):
        return None, None, None
    return rc.get("git_sha"), rc.get("version"), rc.get("migration_head")


def require_rc(payload: dict[str, Any], expected: tuple[Any, Any, Any], *, label: str) -> None:
    actual = rc_identity(payload)
    if actual != expected:
        raise AssemblyV2Error(f"{label} RC identity mismatch: expected {expected}, got {actual}")


def validate_ref(ref: Any, *, label: str) -> dict[str, str]:
    if not isinstance(ref, dict):
        raise AssemblyV2Error(f"{label} must be an object")
    raw_path = ref.get("path")
    expected_hash = ref.get("sha256")
    if not present(raw_path):
        raise AssemblyV2Error(f"{label}.path missing/PENDING")
    if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash.lower()):
        raise AssemblyV2Error(f"{label}.sha256 must be SHA-256")
    path = repo_file(str(raw_path), prefixes=("reports/", "docs/", "evals/", "staging/", "production/", "final/acceptance/"))
    if sha256(path) != expected_hash.lower():
        raise AssemblyV2Error(f"{label} SHA-256 mismatch")
    return frozen(path)


def validate_production_manifest(path: Path) -> tuple[dict[str, Any], tuple[str, str, str]]:
    manifest = load_json(path)
    if manifest.get("schema_version") != 1 or manifest.get("environment") != "production":
        raise AssemblyV2Error("production manifest must be schema-v1 production")
    deployment_id = manifest.get("deployment_id")
    if not present(deployment_id) or path.parent.name != deployment_id:
        raise AssemblyV2Error("production deployment_id must equal manifest parent directory")
    git_sha, version, migration_head = rc_identity(manifest)
    if not isinstance(git_sha, str) or not SHA40.fullmatch(git_sha.lower()):
        raise AssemblyV2Error("production manifest Source RC git_sha must be SHA40")
    if not present(version) or not present(migration_head):
        raise AssemblyV2Error("production manifest Source RC version/migration_head missing")
    edge = manifest.get("edge")
    if not isinstance(edge, dict) or not present(edge.get("domain")):
        raise AssemblyV2Error("production manifest edge.domain missing")
    return manifest, (git_sha.lower(), str(version), str(migration_head))


def validate_governance_policy(path: Path) -> dict[str, str]:
    validator = load_module(GOVERNANCE_POLICY_VALIDATOR, "lumi_governance_policy_v2_assembler")
    try:
        validator.validate_policy(load_json(path))
    except validator.GovernancePolicyError as exc:
        raise AssemblyV2Error(f"repository governance policy invalid: {exc}") from exc
    return frozen(path)


def validate_authorization_request(path: Path, *, release_id: str, expected_rc: tuple[str, str, str]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    validator = load_module(AUTHORIZATION_V2, "lumi_authorization_v2_assembler")
    try:
        request, _policy_path, _policy = validator.validate_request(load_json(path))
    except validator.ReleaseAuthorizationV2Error as exc:
        raise AssemblyV2Error(f"release authorization request invalid: {exc}") from exc
    if request.get("release_id") != release_id:
        raise AssemblyV2Error("release authorization request release_id mismatch")
    source = request.get("source_release_candidate")
    actual = (source.get("git_sha"), source.get("version"), source.get("migration_head")) if isinstance(source, dict) else (None, None, None)
    if actual != expected_rc:
        raise AssemblyV2Error(f"authorization request Source RC mismatch: expected {expected_rc}, got {actual}")
    handoff = request.get("operational_handoff")
    if not isinstance(handoff, dict):
        raise AssemblyV2Error("authorization request operational_handoff missing")
    approvals = {key: "PENDING" for key in APPROVAL_KEYS}
    return frozen(path), approvals, {str(key): str(value) for key, value in handoff.items()}


def validate_upstream(name: str, path: Path, *, expected_rc: tuple[str, str, str], deployment_id: str) -> dict[str, str]:
    decision = load_json(path)
    if decision.get("passed") is not True or not present(decision.get("decision_id")):
        raise AssemblyV2Error(f"upstream {name} is not a concrete passed=true decision")
    require_rc(decision, expected_rc, label=f"upstream {name}")
    if name in {"security", "recovery", "production_deployment"}:
        observed = decision.get("deployment_id")
        if observed is not None and observed != deployment_id:
            raise AssemblyV2Error(f"upstream {name} deployment_id mismatch")
    refs = decision.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        raise AssemblyV2Error(f"upstream {name} lacks frozen evidence_refs")
    for index, ref in enumerate(refs):
        validate_ref(ref, label=f"upstream {name}.evidence_refs[{index}]")
    return frozen(path)


def normalize_scenarios(matrix: dict[str, Any], source: dict[str, Any], *, release_id: str, expected_rc: tuple[str, str, str]) -> list[dict[str, Any]]:
    if source.get("schema_version") != 1 or source.get("release_id") != release_id:
        raise AssemblyV2Error("scenario results schema/release_id mismatch")
    require_rc(source, expected_rc, label="scenario results")
    scenarios = matrix.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise AssemblyV2Error("final acceptance matrix scenarios missing")
    matrix_by_id = {item.get("id"): item for item in scenarios if isinstance(item, dict)}
    if len(matrix_by_id) != len(scenarios) or None in matrix_by_id:
        raise AssemblyV2Error("final acceptance matrix contains duplicate/invalid ids")
    items = source.get("items")
    if not isinstance(items, list):
        raise AssemblyV2Error("scenario results items must be an array")
    source_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise AssemblyV2Error("scenario results contains invalid item")
        if item["id"] in source_by_id:
            raise AssemblyV2Error(f"duplicate scenario result {item['id']}")
        source_by_id[item["id"]] = item
    if set(source_by_id) != set(matrix_by_id):
        raise AssemblyV2Error("scenario result set does not exactly match canonical matrix")
    normalized: list[dict[str, Any]] = []
    blockers: list[str] = []
    for scenario in scenarios:
        scenario_id = scenario["id"]
        item = source_by_id[scenario_id]
        status = item.get("status")
        if status not in FINAL_STATUSES:
            blockers.append(f"{scenario_id} has invalid final status {status!r}")
            continue
        priority = scenario.get("priority")
        severity = scenario.get("severity")
        if priority == "P0" and status != "PASS":
            blockers.append(f"P0 {scenario_id} must PASS")
        if status == "FAIL":
            blockers.append(f"{scenario_id} is FAIL")
        if status in {"BLOCKED_EXTERNAL", "DEFERRED_NON_CRITICAL"} and (priority == "P0" or severity in {"critical", "high"}):
            blockers.append(f"{scenario_id} cannot be deferred/blocked at {priority}/{severity}")
        refs: list[dict[str, str]] = []
        raw_refs = item.get("evidence_refs")
        if status == "PASS":
            if not isinstance(raw_refs, list) or not raw_refs:
                blockers.append(f"{scenario_id} PASS requires frozen evidence_refs")
            else:
                try:
                    refs = [validate_ref(ref, label=f"scenario {scenario_id}.evidence_refs[{index}]") for index, ref in enumerate(raw_refs)]
                except AssemblyV2Error as exc:
                    blockers.append(str(exc))
        elif isinstance(raw_refs, list):
            try:
                refs = [validate_ref(ref, label=f"scenario {scenario_id}.evidence_refs[{index}]") for index, ref in enumerate(raw_refs)]
            except AssemblyV2Error as exc:
                blockers.append(str(exc))
        normalized_item: dict[str, Any] = {"id": scenario_id, "status": status, "evidence_refs": refs, "notes": str(item.get("notes", ""))}
        if status in {"BLOCKED_EXTERNAL", "DEFERRED_NON_CRITICAL"}:
            gap = item.get("gap")
            required = ("owner", "reason", "impact", "target_release", "workaround")
            if not isinstance(gap, dict) or any(not present(gap.get(key)) for key in required):
                blockers.append(f"{scenario_id} deferred/blocked item requires complete gap metadata")
            else:
                normalized_item["gap"] = {key: str(gap[key]) for key in required}
        normalized.append(normalized_item)
    if blockers:
        raise AssemblyV2Error("scenario results are not releasable: " + "; ".join(sorted(set(blockers))))
    return normalized


def assemble(args: argparse.Namespace) -> tuple[Path, Path]:
    matrix_path = repo_file(args.matrix, prefixes=("final/acceptance/",))
    production_path = repo_file(args.production_manifest, prefixes=("reports/production-deployments/",))
    governance_policy_path = repo_file(args.governance_policy, prefixes=("final/acceptance/", "reports/final-acceptance/"))
    authorization_request_path = repo_file(args.authorization_request, prefixes=("reports/final-acceptance/",))
    scenario_path = repo_file(args.scenario_results, prefixes=("reports/final-acceptance/",))
    matrix = load_json(matrix_path)
    production, expected_rc = validate_production_manifest(production_path)
    governance_policy = validate_governance_policy(governance_policy_path)
    release_id = args.release_id
    if not present(release_id) or not re.fullmatch(r"[A-Za-z0-9._-]+", release_id):
        raise AssemblyV2Error("release_id must be a concrete safe identifier")
    authorization_request, approvals, handoff = validate_authorization_request(authorization_request_path, release_id=release_id, expected_rc=expected_rc)
    deployment_id = str(production["deployment_id"])
    upstream_paths = {
        "security": args.security,
        "recovery": args.recovery,
        "performance": args.performance,
        "ai_regression": args.ai_regression,
        "staging_acceptance": args.staging_acceptance,
        "production_deployment": args.production_deployment,
    }
    upstream: dict[str, dict[str, str]] = {}
    for name in UPSTREAM_GATES:
        path = repo_file(upstream_paths[name], prefixes=("reports/",))
        upstream[name] = validate_upstream(name, path, expected_rc=expected_rc, deployment_id=deployment_id)
    items = normalize_scenarios(matrix, load_json(scenario_path), release_id=release_id, expected_rc=expected_rc)
    output_dir = (ROOT / "reports" / "final-acceptance" / release_id).resolve()
    try:
        output_dir.relative_to((ROOT / "reports" / "final-acceptance").resolve())
    except ValueError as exc:
        raise AssemblyV2Error("final output directory escapes reports/final-acceptance") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = output_dir / "acceptance-evidence.json"
    release_path = output_dir / "release-manifest-v2.json"
    evidence = {
        "schema_version": 1,
        "release_id": release_id,
        "release_candidate": production["release_candidate"],
        "assembly_inputs": {"scenario_results": frozen(scenario_path)},
        "items": items,
    }
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    release = {
        "schema_version": 2,
        "kind": "LUMI_FINAL_ACCEPTANCE_PACKAGE_V2",
        "release_id": release_id,
        "release_candidate": production["release_candidate"],
        "production": {
            "deployment_id": deployment_id,
            "domain": production["edge"]["domain"],
            "deployment_manifest_path": repo_relative(production_path),
            "deployment_manifest_sha256": sha256(production_path),
        },
        "repository_governance_policy": governance_policy,
        "release_authorization_request": authorization_request,
        "upstream_gates": upstream,
        "acceptance_evidence": frozen(evidence_path),
        "assembly": {
            "schema_version": 2,
            "assembler": "scripts/final-acceptance-assembler-v2.py",
            "matrix": frozen(matrix_path),
            "scenario_results": frozen(scenario_path),
        },
        "release_blockers": [],
        "approvals": approvals,
        "operational_handoff": handoff,
    }
    release_path.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return release_path, evidence_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble non-cyclic NODE-73 Final Acceptance package V2")
    parser.add_argument("--matrix", default="final/acceptance/manifest-v1.json")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--production-manifest", required=True)
    parser.add_argument("--governance-policy", required=True)
    parser.add_argument("--authorization-request", required=True)
    parser.add_argument("--security", required=True)
    parser.add_argument("--recovery", required=True)
    parser.add_argument("--performance", required=True)
    parser.add_argument("--ai-regression", required=True)
    parser.add_argument("--staging-acceptance", required=True)
    parser.add_argument("--production-deployment", required=True)
    parser.add_argument("--scenario-results", required=True)
    args = parser.parse_args()
    try:
        release_path, evidence_path = assemble(args)
    except (OSError, json.JSONDecodeError, AssemblyV2Error) as exc:
        raise SystemExit(f"final acceptance V2 assembly blocked: {exc}") from exc
    print(json.dumps({"status": "ASSEMBLED_V2", "release": repo_relative(release_path), "evidence": repo_relative(evidence_path), "release_sha256": sha256(release_path), "evidence_sha256": sha256(evidence_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
