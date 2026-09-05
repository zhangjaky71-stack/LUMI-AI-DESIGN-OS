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
GOVERNANCE_VALIDATOR = ROOT / "scripts" / "capture_release_branch_protection.py"
AUTHORIZATION_VALIDATOR = ROOT / "scripts" / "capture_release_authorization.py"
FINAL_STATUSES = {"PASS", "FAIL", "BLOCKED_EXTERNAL", "DEFERRED_NON_CRITICAL"}
UPSTREAM_GATES = (
    "security",
    "recovery",
    "performance",
    "ai_regression",
    "staging_acceptance",
    "production_deployment",
)
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"


class AssemblyError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssemblyError(f"{path} must contain a JSON object")
    return payload


def load_validator(path: Path, name: str, *, label: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssemblyError(f"unable to load canonical {label} validator")
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
        raise AssemblyError(f"path escapes repository: {raw}") from exc
    if not any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in prefixes):
        raise AssemblyError(f"path outside allowed roots: {raw}")
    if not path.is_file():
        raise AssemblyError(f"required file missing: {raw}")
    return path


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise AssemblyError(f"path escapes repository: {path}") from exc


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
        raise AssemblyError(f"{label} RC identity mismatch: expected {expected}, got {actual}")


def validate_ref(ref: Any, *, label: str) -> dict[str, str]:
    if not isinstance(ref, dict):
        raise AssemblyError(f"{label} must be an object")
    raw_path = ref.get("path")
    expected_hash = ref.get("sha256")
    if not present(raw_path):
        raise AssemblyError(f"{label}.path missing/PENDING")
    if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash.lower()):
        raise AssemblyError(f"{label}.sha256 must be SHA-256")
    path = repo_file(
        str(raw_path),
        prefixes=("reports/", "docs/", "evals/", "staging/", "production/"),
    )
    actual_hash = sha256(path)
    if actual_hash != expected_hash.lower():
        raise AssemblyError(f"{label} SHA-256 mismatch")
    return {"path": repo_relative(path), "sha256": actual_hash}


def validate_production_manifest(path: Path) -> tuple[dict[str, Any], tuple[str, str, str]]:
    manifest = load_json(path)
    if manifest.get("schema_version") != 1 or manifest.get("environment") != "production":
        raise AssemblyError("production manifest must be schema-v1 production")
    deployment_id = manifest.get("deployment_id")
    if not present(deployment_id) or path.parent.name != deployment_id:
        raise AssemblyError("production deployment_id must equal manifest parent directory")
    git_sha, version, migration_head = rc_identity(manifest)
    if not isinstance(git_sha, str) or not SHA40.fullmatch(git_sha.lower()):
        raise AssemblyError("production manifest RC git_sha must be SHA40")
    if not present(version) or not present(migration_head):
        raise AssemblyError("production manifest RC version/migration_head missing")
    edge = manifest.get("edge")
    if not isinstance(edge, dict) or not present(edge.get("domain")):
        raise AssemblyError("production manifest edge.domain missing")
    return manifest, (git_sha.lower(), str(version), str(migration_head))


def validate_repository_governance(
    path: Path,
    *,
    expected_release_sha: str,
) -> dict[str, str]:
    report = load_json(path)
    validator = load_validator(
        GOVERNANCE_VALIDATOR,
        "lumi_release_branch_protection",
        label="release branch protection",
    )
    try:
        validator.validate_report(
            report,
            expected_repository=EXPECTED_REPOSITORY,
            expected_release_sha=expected_release_sha,
        )
    except validator.BranchProtectionError as exc:
        raise AssemblyError(f"repository governance invalid: {exc}") from exc
    return frozen(path)


def validate_upstream(
    name: str,
    path: Path,
    *,
    expected_rc: tuple[str, str, str],
    deployment_id: str,
) -> dict[str, str]:
    decision = load_json(path)
    if decision.get("passed") is not True or not present(decision.get("decision_id")):
        raise AssemblyError(f"upstream {name} is not a concrete passed=true decision")
    require_rc(decision, expected_rc, label=f"upstream {name}")
    if name in {"security", "recovery", "production_deployment"}:
        observed_deployment = decision.get("deployment_id")
        if observed_deployment is not None and observed_deployment != deployment_id:
            raise AssemblyError(f"upstream {name} deployment_id mismatch")
    refs = decision.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        raise AssemblyError(f"upstream {name} lacks frozen evidence_refs")
    for index, ref in enumerate(refs):
        validate_ref(ref, label=f"upstream {name}.evidence_refs[{index}]")
    return frozen(path)


def validate_authorization(
    path: Path,
    *,
    release_id: str,
    expected_rc: tuple[str, str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    payload = load_json(path)
    validator = load_validator(
        AUTHORIZATION_VALIDATOR,
        "lumi_release_authorization",
        label="release authorization",
    )
    try:
        validated = validator.validate_authorization_report(
            payload,
            expected_release_id=release_id,
            expected_rc=expected_rc,
        )
    except validator.ReleaseAuthorizationError as exc:
        raise AssemblyError(f"release authorization invalid: {exc}") from exc
    approvals = validated.get("approval_statuses")
    handoff = validated.get("operational_handoff")
    if not isinstance(approvals, dict) or any(value != "APPROVED" for value in approvals.values()):
        raise AssemblyError("canonical release authorization did not yield all APPROVED statuses")
    if not isinstance(handoff, dict):
        raise AssemblyError("canonical release authorization operational handoff is missing")
    return (
        {str(key): str(value) for key, value in approvals.items()},
        {str(key): str(value) for key, value in handoff.items()},
    )


def normalize_scenarios(
    matrix: dict[str, Any],
    source: dict[str, Any],
    *,
    release_id: str,
    expected_rc: tuple[str, str, str],
) -> list[dict[str, Any]]:
    if source.get("schema_version") != 1 or source.get("release_id") != release_id:
        raise AssemblyError("scenario results schema/release_id mismatch")
    require_rc(source, expected_rc, label="scenario results")
    scenarios = matrix.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise AssemblyError("final acceptance matrix scenarios missing")
    matrix_by_id = {item.get("id"): item for item in scenarios if isinstance(item, dict)}
    if len(matrix_by_id) != len(scenarios) or None in matrix_by_id:
        raise AssemblyError("final acceptance matrix contains duplicate/invalid ids")
    items = source.get("items")
    if not isinstance(items, list):
        raise AssemblyError("scenario results items must be an array")
    source_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise AssemblyError("scenario results contains invalid item")
        if item["id"] in source_by_id:
            raise AssemblyError(f"duplicate scenario result {item['id']}")
        source_by_id[item["id"]] = item
    if set(source_by_id) != set(matrix_by_id):
        missing = sorted(set(matrix_by_id) - set(source_by_id))
        extra = sorted(set(source_by_id) - set(matrix_by_id))
        raise AssemblyError(f"scenario result set mismatch; missing={missing}, extra={extra}")

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
        if status in {"BLOCKED_EXTERNAL", "DEFERRED_NON_CRITICAL"} and (
            priority == "P0" or severity in {"critical", "high"}
        ):
            blockers.append(f"{scenario_id} cannot be deferred/blocked at {priority}/{severity}")

        refs_raw = item.get("evidence_refs")
        refs: list[dict[str, str]] = []
        if status == "PASS":
            if not isinstance(refs_raw, list) or not refs_raw:
                blockers.append(f"{scenario_id} PASS requires frozen evidence_refs")
            else:
                try:
                    refs = [
                        validate_ref(ref, label=f"scenario {scenario_id}.evidence_refs[{index}]")
                        for index, ref in enumerate(refs_raw)
                    ]
                except AssemblyError as exc:
                    blockers.append(str(exc))
        elif isinstance(refs_raw, list):
            try:
                refs = [
                    validate_ref(ref, label=f"scenario {scenario_id}.evidence_refs[{index}]")
                    for index, ref in enumerate(refs_raw)
                ]
            except AssemblyError as exc:
                blockers.append(str(exc))

        normalized_item: dict[str, Any] = {
            "id": scenario_id,
            "status": status,
            "evidence_refs": refs,
            "notes": str(item.get("notes", "")),
        }
        if status in {"BLOCKED_EXTERNAL", "DEFERRED_NON_CRITICAL"}:
            gap = item.get("gap")
            required = ("owner", "reason", "impact", "target_release", "workaround")
            if not isinstance(gap, dict) or any(not present(gap.get(key)) for key in required):
                blockers.append(f"{scenario_id} deferred/blocked item requires complete gap metadata")
            else:
                normalized_item["gap"] = {key: str(gap[key]) for key in required}
        normalized.append(normalized_item)

    if blockers:
        raise AssemblyError("scenario results are not releasable: " + "; ".join(sorted(set(blockers))))
    return normalized


def assemble(args: argparse.Namespace) -> tuple[Path, Path]:
    matrix_path = repo_file(args.matrix, prefixes=("final/acceptance/",))
    production_path = repo_file(args.production_manifest, prefixes=("reports/production-deployments/",))
    governance_path = repo_file(args.repository_governance, prefixes=("reports/repository-governance/",))
    authorization_path = repo_file(args.authorization, prefixes=("reports/final-acceptance/",))
    scenario_path = repo_file(args.scenario_results, prefixes=("reports/final-acceptance/",))
    matrix = load_json(matrix_path)
    production, expected_rc = validate_production_manifest(production_path)
    repository_governance = validate_repository_governance(
        governance_path,
        expected_release_sha=expected_rc[0],
    )
    release_id = args.release_id
    if not present(release_id) or not re.fullmatch(r"[A-Za-z0-9._-]+", release_id):
        raise AssemblyError("release_id must be a concrete safe identifier")

    upstream_paths = {
        "security": args.security,
        "recovery": args.recovery,
        "performance": args.performance,
        "ai_regression": args.ai_regression,
        "staging_acceptance": args.staging_acceptance,
        "production_deployment": args.production_deployment,
    }
    upstream: dict[str, dict[str, str]] = {}
    deployment_id = str(production["deployment_id"])
    for name in UPSTREAM_GATES:
        path = repo_file(upstream_paths[name], prefixes=("reports/",))
        upstream[name] = validate_upstream(
            name,
            path,
            expected_rc=expected_rc,
            deployment_id=deployment_id,
        )

    approvals, handoff = validate_authorization(
        authorization_path,
        release_id=release_id,
        expected_rc=expected_rc,
    )
    scenario_source = load_json(scenario_path)
    items = normalize_scenarios(
        matrix,
        scenario_source,
        release_id=release_id,
        expected_rc=expected_rc,
    )

    output_dir = (ROOT / "reports" / "final-acceptance" / release_id).resolve()
    try:
        output_dir.relative_to((ROOT / "reports" / "final-acceptance").resolve())
    except ValueError as exc:
        raise AssemblyError("final output directory escapes reports/final-acceptance") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = output_dir / "acceptance-evidence.json"
    release_path = output_dir / "release.json"

    evidence = {
        "schema_version": 1,
        "release_id": release_id,
        "release_candidate": production["release_candidate"],
        "assembly_inputs": {
            "scenario_results": frozen(scenario_path),
        },
        "items": items,
    }
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    release = {
        "schema_version": 1,
        "release_id": release_id,
        "release_candidate": production["release_candidate"],
        "production": {
            "deployment_id": deployment_id,
            "domain": production["edge"]["domain"],
            "deployment_manifest_path": repo_relative(production_path),
            "deployment_manifest_sha256": sha256(production_path),
        },
        "repository_governance": repository_governance,
        "upstream_gates": upstream,
        "acceptance_evidence": frozen(evidence_path),
        "release_authorization": frozen(authorization_path),
        "assembly": {
            "schema_version": 1,
            "assembler": "scripts/final-acceptance-assembler.py",
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
    parser = argparse.ArgumentParser(description="Assemble a fail-closed NODE-73 final acceptance package")
    parser.add_argument("--matrix", default="final/acceptance/manifest-v1.json")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--production-manifest", required=True)
    parser.add_argument("--repository-governance", required=True)
    parser.add_argument("--security", required=True)
    parser.add_argument("--recovery", required=True)
    parser.add_argument("--performance", required=True)
    parser.add_argument("--ai-regression", required=True)
    parser.add_argument("--staging-acceptance", required=True)
    parser.add_argument("--production-deployment", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--scenario-results", required=True)
    args = parser.parse_args()
    try:
        release_path, evidence_path = assemble(args)
    except (OSError, json.JSONDecodeError, AssemblyError) as exc:
        raise SystemExit(f"final acceptance assembly blocked: {exc}") from exc
    print(json.dumps({
        "status": "ASSEMBLED",
        "release": repo_relative(release_path),
        "evidence": repo_relative(evidence_path),
        "release_sha256": sha256(release_path),
        "evidence_sha256": sha256(evidence_path),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
