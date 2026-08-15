#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FINAL_STATUSES = {"PASS", "FAIL", "BLOCKED_EXTERNAL", "DEFERRED_NON_CRITICAL"}
IDENTITY_GATES = {"performance", "ai_regression", "staging_acceptance", "production_deployment"}


class FinalAcceptanceError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FinalAcceptanceError(f"{path} must contain a JSON object")
    return payload


def present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def canonical_repo_path(value: str, *, allowed_prefixes: tuple[str, ...]) -> Path:
    candidate = (ROOT / value).resolve()
    try:
        relative = candidate.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise FinalAcceptanceError(f"evidence path escapes repository: {value}") from exc
    if not any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in allowed_prefixes):
        raise FinalAcceptanceError(f"evidence path is outside allowed roots: {value}")
    return candidate


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_file(
    spec: dict[str, Any],
    *,
    label: str,
    allowed_prefixes: tuple[str, ...],
    blockers: list[str],
) -> Path | None:
    path_value = spec.get("path") if isinstance(spec, dict) else None
    hash_value = spec.get("sha256") if isinstance(spec, dict) else None
    if not present(path_value):
        blockers.append(f"{label}.path is missing/PENDING")
        return None
    if not isinstance(hash_value, str) or not SHA256.fullmatch(hash_value.lower()):
        blockers.append(f"{label}.sha256 must be an exact SHA-256")
        return None
    try:
        path = canonical_repo_path(str(path_value), allowed_prefixes=allowed_prefixes)
    except FinalAcceptanceError as exc:
        blockers.append(str(exc))
        return None
    if not path.is_file():
        blockers.append(f"{label} evidence file does not exist: {path_value}")
        return None
    actual = digest(path)
    if actual != hash_value.lower():
        blockers.append(f"{label} SHA-256 mismatch: expected {hash_value.lower()}, got {actual}")
        return None
    return path


def rc_identity(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    rc = payload.get("release_candidate")
    if not isinstance(rc, dict):
        return None, None, None
    return rc.get("git_sha"), rc.get("version"), rc.get("migration_head")


def validate_release_manifest(manifest: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if manifest.get("schema_version") != 1:
        blockers.append("release manifest schema_version must be 1")
    if not present(manifest.get("release_id")):
        blockers.append("release_id is missing/PENDING")

    rc = manifest.get("release_candidate")
    if not isinstance(rc, dict):
        blockers.append("release_candidate object missing")
    else:
        sha = rc.get("git_sha")
        if not isinstance(sha, str) or not SHA40.fullmatch(sha.lower()):
            blockers.append("release_candidate.git_sha must be exact SHA40")
        for key in ("version", "migration_head"):
            if not present(rc.get(key)):
                blockers.append(f"release_candidate.{key} is missing/PENDING")

    required_upstream = set(matrix.get("required_upstream_gates", []))
    upstream = manifest.get("upstream_gates")
    if not isinstance(upstream, dict) or set(upstream) != required_upstream:
        blockers.append(f"upstream_gates must contain exactly {sorted(required_upstream)}")

    production = manifest.get("production")
    if not isinstance(production, dict):
        blockers.append("production object missing")
    else:
        for key in ("deployment_id", "domain"):
            if not present(production.get(key)):
                blockers.append(f"production.{key} is missing/PENDING")
        dm_path = production.get("deployment_manifest_path")
        dm_sha = production.get("deployment_manifest_sha256")
        if not present(dm_path):
            blockers.append("production.deployment_manifest_path is missing/PENDING")
        if not isinstance(dm_sha, str) or not SHA256.fullmatch(dm_sha.lower()):
            blockers.append("production.deployment_manifest_sha256 must be SHA-256")

    release_blockers = manifest.get("release_blockers")
    if not isinstance(release_blockers, list):
        blockers.append("release_blockers must be an array")
    elif release_blockers:
        blockers.append(f"unresolved release_blockers must be zero; found {len(release_blockers)}")

    approvals = manifest.get("approvals")
    required_approvals = {"product", "engineering", "security", "operations", "release_owner"}
    if not isinstance(approvals, dict) or set(approvals) != required_approvals:
        blockers.append(f"approvals must contain exactly {sorted(required_approvals)}")
    else:
        for name, status in approvals.items():
            if status != "APPROVED":
                blockers.append(f"approval {name} is not APPROVED")

    handoff = manifest.get("operational_handoff")
    required_handoff = {
        "on_call_owner",
        "support_owner",
        "incident_commander_rotation",
        "first_day_watch_owner",
        "quality_cost_review_owner",
        "security_dependency_review_owner",
        "dr_drill_owner",
        "capacity_review_owner",
    }
    if not isinstance(handoff, dict) or set(handoff) != required_handoff:
        blockers.append(f"operational_handoff must contain exactly {sorted(required_handoff)}")
    else:
        for name, value in handoff.items():
            if not present(value):
                blockers.append(f"operational_handoff.{name} is missing/PENDING")
    return blockers


def validate_upstream_gates(manifest: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    upstream = manifest.get("upstream_gates")
    if not isinstance(upstream, dict):
        return ["upstream_gates object missing"]
    expected_rc = rc_identity(manifest)
    for name in matrix.get("required_upstream_gates", []):
        spec = upstream.get(name)
        if not isinstance(spec, dict):
            blockers.append(f"upstream gate {name} spec missing")
            continue
        path = verify_frozen_file(
            spec,
            label=f"upstream_gates.{name}",
            allowed_prefixes=("reports/",),
            blockers=blockers,
        )
        if path is None:
            continue
        try:
            decision = load_json(path)
        except (OSError, json.JSONDecodeError, FinalAcceptanceError) as exc:
            blockers.append(f"upstream gate {name} decision invalid: {exc}")
            continue
        if not present(decision.get("decision_id")):
            blockers.append(f"upstream gate {name} lacks a concrete decision_id")
        if decision.get("passed") is not True:
            blockers.append(f"upstream gate {name} is not passed=true")

        refs = decision.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            blockers.append(f"upstream gate {name} must contain frozen evidence_refs")
        else:
            for index, ref in enumerate(refs):
                if not isinstance(ref, dict):
                    blockers.append(f"upstream gate {name} evidence_refs[{index}] must be an object")
                    continue
                verify_frozen_file(
                    ref,
                    label=f"upstream gate {name}.evidence_refs[{index}]",
                    allowed_prefixes=("reports/", "docs/", "evals/", "staging/", "production/"),
                    blockers=blockers,
                )

        if name in IDENTITY_GATES:
            actual_rc = rc_identity(decision)
            if any(value is None for value in actual_rc):
                blockers.append(f"upstream gate {name} lacks release_candidate identity")
            elif actual_rc != expected_rc:
                blockers.append(
                    f"upstream gate {name} RC identity mismatch: expected {expected_rc}, got {actual_rc}"
                )
    return blockers


def validate_production_manifest(manifest: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    production = manifest.get("production")
    if not isinstance(production, dict):
        return ["production object missing"]
    spec = {
        "path": production.get("deployment_manifest_path"),
        "sha256": production.get("deployment_manifest_sha256"),
    }
    path = verify_frozen_file(
        spec,
        label="production.deployment_manifest",
        allowed_prefixes=("reports/production-deployments/",),
        blockers=blockers,
    )
    if path is None:
        return blockers
    try:
        deployment = load_json(path)
    except (OSError, json.JSONDecodeError, FinalAcceptanceError) as exc:
        return blockers + [f"production deployment manifest invalid: {exc}"]
    if deployment.get("deployment_id") != production.get("deployment_id"):
        blockers.append("production deployment_id does not match frozen deployment manifest")
    if rc_identity(deployment) != rc_identity(manifest):
        blockers.append("production deployment manifest RC identity does not match final release")
    return blockers


def validate_gap_metadata(item: dict[str, Any], *, scenario_id: str) -> list[str]:
    gap = item.get("gap")
    required = ("owner", "reason", "impact", "target_release", "workaround")
    if not isinstance(gap, dict):
        return [f"{scenario_id} deferred/blocked non-critical item requires gap metadata"]
    return [f"{scenario_id} gap.{key} is missing" for key in required if not present(gap.get(key))]


def validate_acceptance_evidence(
    matrix: dict[str, Any],
    release: dict[str, Any],
    evidence: dict[str, Any],
    evidence_path: Path,
) -> tuple[list[str], dict[str, int]]:
    blockers: list[str] = []
    if evidence.get("schema_version") != 1:
        blockers.append("acceptance evidence schema_version must be 1")
    if evidence.get("release_id") != release.get("release_id"):
        blockers.append("acceptance evidence release_id does not match release manifest")
    if rc_identity(evidence) != rc_identity(release):
        blockers.append("acceptance evidence RC identity does not match release manifest")

    frozen = release.get("acceptance_evidence")
    if not isinstance(frozen, dict):
        blockers.append("release acceptance_evidence freeze spec missing")
    else:
        configured = frozen.get("path")
        try:
            relative = evidence_path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            relative = "<outside-repository>"
        if configured != relative:
            blockers.append("release acceptance_evidence.path does not match evaluated evidence file")
        if not isinstance(frozen.get("sha256"), str) or not SHA256.fullmatch(str(frozen.get("sha256", "")).lower()):
            blockers.append("release acceptance_evidence.sha256 must be SHA-256")
        elif evidence_path.is_file() and digest(evidence_path) != frozen["sha256"].lower():
            blockers.append("acceptance evidence SHA-256 does not match frozen release manifest")

    scenarios = matrix.get("scenarios")
    if not isinstance(scenarios, list):
        return blockers + ["acceptance matrix scenarios missing"], {}
    scenario_by_id = {item.get("id"): item for item in scenarios if isinstance(item, dict)}
    if len(scenario_by_id) != len(scenarios) or None in scenario_by_id:
        blockers.append("acceptance matrix has duplicate/invalid scenario ids")

    items = evidence.get("items")
    if not isinstance(items, list):
        return blockers + ["acceptance evidence items must be an array"], {}
    item_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            blockers.append("acceptance evidence contains invalid item")
            continue
        if item["id"] in item_by_id:
            blockers.append(f"duplicate acceptance evidence id {item['id']}")
        item_by_id[item["id"]] = item
    if set(item_by_id) != set(scenario_by_id):
        missing = sorted(set(scenario_by_id) - set(item_by_id))
        extra = sorted(set(item_by_id) - set(scenario_by_id))
        blockers.append(f"acceptance evidence scenario set mismatch; missing={missing}, extra={extra}")

    counts = {status: 0 for status in sorted(FINAL_STATUSES)}
    for scenario_id, scenario in scenario_by_id.items():
        item = item_by_id.get(scenario_id)
        if item is None:
            continue
        status = item.get("status")
        if status not in FINAL_STATUSES:
            blockers.append(f"{scenario_id} has invalid/finally-unset status {status!r}")
            continue
        counts[status] += 1
        priority = scenario.get("priority")
        severity = scenario.get("severity")

        if priority == "P0" and status != "PASS":
            blockers.append(f"P0 {scenario_id} must PASS, got {status}")
        if status == "FAIL":
            blockers.append(f"{scenario_id} is FAIL")
        if status in {"DEFERRED_NON_CRITICAL", "BLOCKED_EXTERNAL"}:
            if priority == "P0" or severity in {"critical", "high"}:
                blockers.append(f"{scenario_id} cannot be deferred/blocked at {priority}/{severity}")
            blockers.extend(validate_gap_metadata(item, scenario_id=scenario_id))

        refs = item.get("evidence_refs")
        if status == "PASS":
            if not isinstance(refs, list) or not refs:
                blockers.append(f"{scenario_id} PASS requires at least one frozen evidence_ref")
                continue
            for index, ref in enumerate(refs):
                if not isinstance(ref, dict):
                    blockers.append(f"{scenario_id} evidence_refs[{index}] must be an object")
                    continue
                verify_frozen_file(
                    ref,
                    label=f"{scenario_id}.evidence_refs[{index}]",
                    allowed_prefixes=("reports/", "docs/", "evals/", "staging/", "production/"),
                    blockers=blockers,
                )
    return blockers, counts


def evaluate(
    matrix: dict[str, Any],
    release: dict[str, Any],
    evidence: dict[str, Any],
    evidence_path: Path,
) -> dict[str, Any]:
    blockers = validate_release_manifest(release, matrix)
    blockers.extend(validate_upstream_gates(release, matrix))
    blockers.extend(validate_production_manifest(release))
    evidence_blockers, counts = validate_acceptance_evidence(matrix, release, evidence, evidence_path)
    blockers.extend(evidence_blockers)
    blockers = sorted(set(blockers))
    accepted = not blockers
    payload = {
        "schema_version": 1,
        "release_id": release.get("release_id"),
        "release_candidate": release.get("release_candidate", {}),
        "production": release.get("production", {}),
        "accepted": accepted,
        "passed": accepted,
        "headline": (
            "LUMI AI DESIGN OS — PRODUCT ACCEPTED"
            if accepted
            else "NOT ACCEPTED — SEE BLOCKING GAPS"
        ),
        "status_counts": counts,
        "blockers": blockers,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {"decision_id": hashlib.sha256(canonical.encode()).hexdigest()[:24], **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate LUMI NODE-73 final product acceptance")
    parser.add_argument("--matrix", default="final/acceptance/manifest-v1.json")
    parser.add_argument("--release", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        matrix_path = canonical_repo_path(args.matrix, allowed_prefixes=("final/acceptance/",))
        release_path = canonical_repo_path(args.release, allowed_prefixes=("reports/final-acceptance/",))
        evidence_path = canonical_repo_path(args.evidence, allowed_prefixes=("reports/final-acceptance/",))
        result = evaluate(load_json(matrix_path), load_json(release_path), load_json(evidence_path), evidence_path)
    except (OSError, json.JSONDecodeError, FinalAcceptanceError) as exc:
        raise SystemExit(f"final acceptance input invalid: {exc}") from exc

    output = canonical_repo_path(args.output, allowed_prefixes=("reports/final-acceptance/",))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": result["accepted"], "decision_id": result["decision_id"], "headline": result["headline"]}, ensure_ascii=False, sort_keys=True))
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
