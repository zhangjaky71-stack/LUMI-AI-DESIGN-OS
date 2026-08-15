#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "staging" / "acceptance" / "manifest-v1.json"
PARITY = ROOT / "staging" / "acceptance" / "environment-parity-v1.json"
TEMPLATE = ROOT / "staging" / "acceptance" / "evidence-template.json"
GATE = ROOT / "scripts" / "staging-acceptance-gate.py"


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{path} must be an object")
    return raw


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_staging_acceptance_gate", GATE)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import staging acceptance gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"staging acceptance contract invalid: {message}")


def clean_evidence(manifest: dict[str, Any], parity: dict[str, Any]) -> dict[str, Any]:
    scenarios = manifest["scenarios"]
    parity_checks = parity["required_checks"]
    return {
        "schema_version": 1,
        "manifest_id": manifest["manifest_id"],
        "release_candidate": {
            "git_sha": "c" * 40,
            "version": "0.0.0-rc.contract",
            "environment_id": "staging-contract-fixture",
            "base_url": "https://staging.example.invalid",
            "container_image_set_ref": "fixture-image-set@sha256:contract",
            "migration_head": "fixture-migration-head",
        },
        "data_policy": {
            "production_customer_data_used": False,
            "test_data_only": True,
            "staging_secrets_isolated": True,
        },
        "test_accounts": {
            "org_a_owner": "fixture:org-a-owner",
            "org_a_editor": "fixture:org-a-editor",
            "org_a_viewer": "fixture:org-a-viewer",
            "org_b_owner": "fixture:org-b-owner",
            "platform_ops": "fixture:platform-ops",
            "billing_test_org": "fixture:billing-org",
        },
        "provider_modes": {
            "mock_provider": "AVAILABLE",
            "provider_sandbox": "AVAILABLE",
            "production_candidate_quality_sample": "AVAILABLE",
        },
        "environment_parity": {
            item["id"]: {"status": "PASS", "evidence_ref": f"fixture:parity:{item['id']}"}
            for item in parity_checks
        },
        "scenario_results": {
            item["id"]: {
                "status": "PASS",
                "actual": "contract fixture matched expected behavior",
                "evidence_ref": f"fixture:scenario:{item['id']}",
                "owner": "contract-test",
            }
            for item in scenarios
        },
        "open_issues": [],
        "approvals": {
            "engineering": "APPROVED",
            "security": "APPROVED",
            "product": "APPROVED",
            "release_owner": "APPROVED",
        },
    }


def main() -> int:
    manifest = load_json(MANIFEST)
    parity = load_json(PARITY)
    template = load_json(TEMPLATE)
    gate = load_gate()

    scenarios = manifest.get("scenarios")
    require(isinstance(scenarios, list) and len(scenarios) >= 25, "acceptance manifest must cover the full product surface")
    ids = [item.get("id") for item in scenarios]
    require(len(ids) == len(set(ids)), "scenario IDs must be unique")
    require(all(item.get("priority") in {"P0", "P1"} for item in scenarios), "scenario priorities must be P0/P1")
    require(all(item.get("severity") in {"critical", "high", "medium", "low"} for item in scenarios), "scenario severities invalid")

    pending = gate.evaluate(manifest, parity, template)
    require(pending["passed"] is False, "empty evidence template must never pass")
    require(pending["summary"]["p0_passed"] == 0, "empty template must have zero P0 passes")

    clean = clean_evidence(manifest, parity)
    decision = gate.evaluate(manifest, parity, clean)
    require(decision["passed"] is True, "complete contract fixture must be able to pass")
    require(decision["summary"]["p0_passed"] == decision["summary"]["p0_total"], "all P0 fixtures must pass")

    not_run = copy.deepcopy(clean)
    not_run["scenario_results"]["E2E-01"] = {"status": "NOT_RUN"}
    require(gate.evaluate(manifest, parity, not_run)["passed"] is False, "P0 NOT_RUN must block")

    fake_pass = copy.deepcopy(clean)
    fake_pass["scenario_results"]["E2E-02"] = {"status": "PASS", "actual": "ok", "owner": "contract-test"}
    require(gate.evaluate(manifest, parity, fake_pass)["passed"] is False, "PASS without evidence_ref must block")

    invalid_external = copy.deepcopy(clean)
    invalid_external["scenario_results"]["SEC-01"] = {
        "status": "BLOCKED_EXTERNAL",
        "actual": "dependency missing",
        "evidence_ref": "fixture:ticket:1",
        "owner": "contract-test",
        "external_reason": "fixture dependency",
    }
    invalid_external_decision = gate.evaluate(manifest, parity, invalid_external)
    require(invalid_external_decision["passed"] is False, "non-external scenario cannot use BLOCKED_EXTERNAL")
    require(any("invalid BLOCKED_EXTERNAL" in item for item in invalid_external_decision["blockers"]), "invalid external status must be explicit")

    external_p0 = copy.deepcopy(clean)
    external_p0["scenario_results"]["AI-01"] = {
        "status": "BLOCKED_EXTERNAL",
        "actual": "provider credential unavailable",
        "evidence_ref": "fixture:external:provider",
        "owner": "release-owner",
        "external_reason": "provider account unavailable",
    }
    require(gate.evaluate(manifest, parity, external_p0)["passed"] is False, "P0 BLOCKED_EXTERNAL must still block go-live")

    critical_issue = copy.deepcopy(clean)
    critical_issue["open_issues"] = [{"id": "FIX-1", "severity": "critical", "status": "OPEN", "owner": "contract-test"}]
    require(gate.evaluate(manifest, parity, critical_issue)["passed"] is False, "open critical issue must block")

    parity_fail = copy.deepcopy(clean)
    parity_fail["environment_parity"]["PARITY-IMAGE"] = {"status": "FAIL", "evidence_ref": "fixture:parity:bad"}
    require(gate.evaluate(manifest, parity, parity_fail)["passed"] is False, "environment parity failure must block")

    output = {
        "status": "PASS",
        "manifest_id": manifest["manifest_id"],
        "scenario_count": len(scenarios),
        "p0_count": decision["summary"]["p0_total"],
        "parity_count": decision["summary"]["parity_total"],
        "clean_fixture_decision": decision["decision_id"],
        "drills": {
            "empty_template_blocked": True,
            "p0_not_run_blocked": True,
            "unevidenced_pass_blocked": True,
            "invalid_external_blocked": True,
            "p0_external_still_blocks": True,
            "critical_issue_blocked": True,
            "parity_failure_blocked": True,
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
