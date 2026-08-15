#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "final-acceptance-gate.py"
FIXTURE_ROOT = ROOT / "reports" / "final-acceptance" / "_node73-contract-fixture"
PROD_FIXTURE_ROOT = ROOT / "reports" / "production-deployments" / "_node73-contract-fixture"


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_final_acceptance_gate", GATE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import final acceptance gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"final acceptance contract invalid: {message}")


def rc() -> dict[str, str]:
    return {
        "git_sha": "c" * 40,
        "version": "1.0.0-rc.1",
        "migration_head": "20260815_001",
    }


def make_fixture(matrix: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Path]]:
    evidence_atom = FIXTURE_ROOT / "evidence" / "contract-proof.json"
    write_json(evidence_atom, {"schema_version": 1, "kind": "NODE-73-CONTRACT-FIXTURE", "passed": True})
    evidence_ref = {"path": repo_path(evidence_atom), "sha256": sha(evidence_atom)}

    items = []
    for scenario in matrix["scenarios"]:
        items.append({
            "id": scenario["id"],
            "status": "PASS",
            "evidence_refs": [copy.deepcopy(evidence_ref)],
            "notes": "Contract fixture only; not production evidence.",
        })
    evidence = {
        "schema_version": 1,
        "release_id": "final-contract-001",
        "release_candidate": rc(),
        "items": items,
    }
    evidence_path = FIXTURE_ROOT / "acceptance-evidence.json"
    write_json(evidence_path, evidence)

    upstream_paths: dict[str, Path] = {}
    upstream_specs: dict[str, dict[str, str]] = {}
    for name in matrix["required_upstream_gates"]:
        path = FIXTURE_ROOT / "upstream" / f"{name}.json"
        payload: dict[str, Any] = {
            "schema_version": 1,
            "passed": True,
            "decision_id": f"{name}-contract",
            "evidence_refs": [copy.deepcopy(evidence_ref)],
            "blockers": [],
        }
        if name in {"performance", "ai_regression", "staging_acceptance", "production_deployment"}:
            payload["release_candidate"] = rc()
        write_json(path, payload)
        upstream_paths[name] = path
        upstream_specs[name] = {"path": repo_path(path), "sha256": sha(path)}

    deployment_manifest = PROD_FIXTURE_ROOT / "manifest.json"
    write_json(deployment_manifest, {
        "schema_version": 1,
        "deployment_id": "prod-contract-001",
        "release_candidate": rc(),
    })

    release = {
        "schema_version": 1,
        "release_id": "final-contract-001",
        "release_candidate": rc(),
        "production": {
            "deployment_id": "prod-contract-001",
            "domain": "app.example.com",
            "deployment_manifest_path": repo_path(deployment_manifest),
            "deployment_manifest_sha256": sha(deployment_manifest),
        },
        "upstream_gates": upstream_specs,
        "acceptance_evidence": {"path": repo_path(evidence_path), "sha256": sha(evidence_path)},
        "release_blockers": [],
        "approvals": {
            "product": "APPROVED",
            "engineering": "APPROVED",
            "security": "APPROVED",
            "operations": "APPROVED",
            "release_owner": "APPROVED",
        },
        "operational_handoff": {
            "on_call_owner": "platform-on-call",
            "support_owner": "support-owner",
            "incident_commander_rotation": "incident-rotation",
            "first_day_watch_owner": "release-owner",
            "quality_cost_review_owner": "ai-ops-owner",
            "security_dependency_review_owner": "security-owner",
            "dr_drill_owner": "reliability-owner",
            "capacity_review_owner": "platform-owner",
        },
    }
    return release, evidence, evidence_path, upstream_paths


def evaluate_case(gate: ModuleType, matrix: dict[str, Any], release: dict[str, Any], evidence: dict[str, Any], evidence_path: Path) -> dict[str, Any]:
    write_json(evidence_path, evidence)
    release["acceptance_evidence"]["sha256"] = sha(evidence_path)
    return gate.evaluate(matrix, release, evidence, evidence_path)


def main() -> int:
    gate = load_gate()
    matrix = json.loads((ROOT / "final" / "acceptance" / "manifest-v1.json").read_text(encoding="utf-8"))
    require(len(matrix.get("scenarios", [])) == 46, "final matrix must contain exactly 46 scenarios")
    require(len({item["id"] for item in matrix["scenarios"]}) == len(matrix["scenarios"]), "duplicate scenario id")
    require(all(item["priority"] in {"P0", "P1", "P2"} for item in matrix["scenarios"]), "invalid priority")

    for root in (FIXTURE_ROOT, PROD_FIXTURE_ROOT):
        if root.exists():
            shutil.rmtree(root)
    try:
        clean_release, clean_evidence, evidence_path, upstream_paths = make_fixture(matrix)
        clean = evaluate_case(gate, matrix, copy.deepcopy(clean_release), copy.deepcopy(clean_evidence), evidence_path)
        require(clean["accepted"] is True, f"clean contract fixture must accept: {clean['blockers']}")
        require(clean["headline"] == "LUMI AI DESIGN OS — PRODUCT ACCEPTED", "accepted headline mismatch")

        first_p0 = next(item["id"] for item in matrix["scenarios"] if item["priority"] == "P0")
        fail_evidence = copy.deepcopy(clean_evidence)
        next(item for item in fail_evidence["items"] if item["id"] == first_p0)["status"] = "FAIL"
        result = evaluate_case(gate, matrix, copy.deepcopy(clean_release), fail_evidence, evidence_path)
        require(result["accepted"] is False and any("must PASS" in blocker for blocker in result["blockers"]), "P0 FAIL must block")

        blocked_evidence = copy.deepcopy(clean_evidence)
        item = next(item for item in blocked_evidence["items"] if item["id"] == first_p0)
        item["status"] = "BLOCKED_EXTERNAL"
        item["gap"] = {"owner":"ops","reason":"external","impact":"P0","target_release":"1.0","workaround":"none"}
        require(evaluate_case(gate, matrix, copy.deepcopy(clean_release), blocked_evidence, evidence_path)["accepted"] is False, "P0 BLOCKED_EXTERNAL must block")

        p1 = next(item for item in matrix["scenarios"] if item["priority"] == "P1" and item["severity"] not in {"critical", "high"})
        deferred = copy.deepcopy(clean_evidence)
        item = next(item for item in deferred["items"] if item["id"] == p1["id"])
        item["status"] = "DEFERRED_NON_CRITICAL"
        item["evidence_refs"] = []
        item["gap"] = {
            "owner": "product-owner",
            "reason": "Non-critical follow-up",
            "impact": "No P0 launch impact",
            "target_release": "1.1",
            "workaround": "Documented supported path",
        }
        require(evaluate_case(gate, matrix, copy.deepcopy(clean_release), deferred, evidence_path)["accepted"] is True, "complete P1 defer should be allowed")

        bad_defer = copy.deepcopy(deferred)
        next(item for item in bad_defer["items"] if item["id"] == p1["id"])["gap"].pop("owner")
        require(evaluate_case(gate, matrix, copy.deepcopy(clean_release), bad_defer, evidence_path)["accepted"] is False, "defer without owner must block")

        no_evidence = copy.deepcopy(clean_evidence)
        next(item for item in no_evidence["items"] if item["id"] == first_p0)["evidence_refs"] = []
        require(evaluate_case(gate, matrix, copy.deepcopy(clean_release), no_evidence, evidence_path)["accepted"] is False, "PASS without evidence must block")

        release_blocked = copy.deepcopy(clean_release)
        release_blocked["release_blockers"] = [{"id": "STOP-001", "reason": "open blocker"}]
        require(evaluate_case(gate, matrix, release_blocked, copy.deepcopy(clean_evidence), evidence_path)["accepted"] is False, "open release blocker must block")

        approval_missing = copy.deepcopy(clean_release)
        approval_missing["approvals"]["security"] = "PENDING"
        require(evaluate_case(gate, matrix, approval_missing, copy.deepcopy(clean_evidence), evidence_path)["accepted"] is False, "missing approval must block")

        security_path = upstream_paths["security"]
        security_payload = json.loads(security_path.read_text(encoding="utf-8"))
        security_payload["passed"] = False
        write_json(security_path, security_payload)
        upstream_false = copy.deepcopy(clean_release)
        upstream_false["upstream_gates"]["security"]["sha256"] = sha(security_path)
        require(evaluate_case(gate, matrix, upstream_false, copy.deepcopy(clean_evidence), evidence_path)["accepted"] is False, "upstream passed=false must block")
        security_payload["passed"] = True
        write_json(security_path, security_payload)

        upstream_no_refs_payload = copy.deepcopy(security_payload)
        upstream_no_refs_payload["evidence_refs"] = []
        write_json(security_path, upstream_no_refs_payload)
        upstream_no_refs = copy.deepcopy(clean_release)
        upstream_no_refs["upstream_gates"]["security"]["sha256"] = sha(security_path)
        require(evaluate_case(gate, matrix, upstream_no_refs, copy.deepcopy(clean_evidence), evidence_path)["accepted"] is False, "upstream decision without evidence refs must block")
        write_json(security_path, security_payload)

        upstream_hash_bad = copy.deepcopy(clean_release)
        upstream_hash_bad["upstream_gates"]["security"]["sha256"] = "0" * 64
        require(evaluate_case(gate, matrix, upstream_hash_bad, copy.deepcopy(clean_evidence), evidence_path)["accepted"] is False, "upstream SHA mismatch must block")

        staging_path = upstream_paths["staging_acceptance"]
        staging_payload = json.loads(staging_path.read_text(encoding="utf-8"))
        staging_payload["release_candidate"]["git_sha"] = "e" * 40
        write_json(staging_path, staging_payload)
        rc_swap = copy.deepcopy(clean_release)
        rc_swap["upstream_gates"]["staging_acceptance"]["sha256"] = sha(staging_path)
        require(evaluate_case(gate, matrix, rc_swap, copy.deepcopy(clean_evidence), evidence_path)["accepted"] is False, "upstream RC swap must block")

        deployment_path = ROOT / clean_release["production"]["deployment_manifest_path"]
        deployment_payload = json.loads(deployment_path.read_text(encoding="utf-8"))
        deployment_payload["release_candidate"]["version"] = "different"
        write_json(deployment_path, deployment_payload)
        prod_swap = copy.deepcopy(clean_release)
        prod_swap["production"]["deployment_manifest_sha256"] = sha(deployment_path)
        require(evaluate_case(gate, matrix, prod_swap, copy.deepcopy(clean_evidence), evidence_path)["accepted"] is False, "production deployment RC swap must block")

        frozen_mismatch = copy.deepcopy(clean_release)
        frozen_mismatch["acceptance_evidence"]["sha256"] = "f" * 64
        write_json(evidence_path, clean_evidence)
        result = gate.evaluate(matrix, frozen_mismatch, clean_evidence, evidence_path)
        require(result["accepted"] is False, "acceptance evidence SHA mismatch must block")

        print(json.dumps({
            "status": "PASS",
            "clean_decision_id": clean["decision_id"],
            "scenario_count": len(matrix["scenarios"]),
            "drills": {
                "p0_fail_blocked": True,
                "p0_blocked_external_blocked": True,
                "p1_complete_defer_allowed": True,
                "p1_incomplete_defer_blocked": True,
                "pass_without_evidence_blocked": True,
                "open_release_blocker_blocked": True,
                "missing_approval_blocked": True,
                "upstream_false_blocked": True,
                "upstream_missing_evidence_blocked": True,
                "upstream_hash_swap_blocked": True,
                "upstream_rc_swap_blocked": True,
                "production_rc_swap_blocked": True,
                "acceptance_hash_swap_blocked": True
            }
        }, indent=2, sort_keys=True))
        return 0
    finally:
        for root in (FIXTURE_ROOT, PROD_FIXTURE_ROOT):
            if root.exists():
                shutil.rmtree(root)


if __name__ == "__main__":
    raise SystemExit(main())
