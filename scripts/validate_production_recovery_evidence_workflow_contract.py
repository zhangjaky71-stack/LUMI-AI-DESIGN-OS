#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DR = ROOT / ".github" / "workflows" / "production-dr-rehearsal.yml"
FREEZE = ROOT / ".github" / "workflows" / "freeze-production-recovery-evidence.yml"
ASSEMBLER = ROOT / ".github" / "workflows" / "assemble-final-acceptance.yml"
FROZEN_VALIDATOR = ROOT / "scripts" / "validate_frozen_production_recovery_evidence.py"
PINS = ROOT / "production" / "release-actions" / "pins-v1.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*-\s+uses:\s+([^\s#]+)(?:\s+#\s*(\S+))?\s*$", re.MULTILINE)


class RecoveryWorkflowContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RecoveryWorkflowContractError(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def require_sha_pins(text: str, label: str) -> int:
    matches = list(USES.finditer(text))
    require(bool(matches), f"{label} must use external Actions")
    for match in matches:
        target = match.group(1)
        version = match.group(2)
        require("@" in target, f"{label} action missing @ref: {target}")
        _action, ref = target.rsplit("@", 1)
        require(SHA40.fullmatch(ref) is not None, f"{label} action is not immutable SHA40: {target}")
        require(isinstance(version, str) and version.startswith("v"), f"{label} action is missing version annotation: {target}")
    return len(matches)


def validate_dr() -> None:
    text = DR.read_text(encoding="utf-8")
    require_sha_pins(text, "Production DR Rehearsal")
    markers = (
        "permissions:\n  contents: read\n  id-token: write",
        "environment: production",
        'test "$GITHUB_REF_NAME" = "release-closure-p0"',
        'ref: ${{ github.sha }}',
        "fetch-depth: 0",
        "persist-credentials: false",
        'git merge-base --is-ancestor "$SOURCE_RC_SHA" "$GITHUB_SHA"',
        'git merge-base --is-ancestor "$RC_SHA" "$GITHUB_SHA"',
        "restore-db-instance-to-point-in-time",
        "--no-publicly-accessible",
        'assignPublicIp:"DISABLED"',
        'command:["python3","scripts/production-recovery-db-verify.py"]',
        'database_evidence_source_versions_remaining',
        'database_evidence_recovery_versions_remaining',
        "python3 scripts/production-recovery-decision.py",
        "production-dr-${{ needs.recovery-gate.outputs.deployment_id }}-${{ github.run_id }}",
    )
    for marker in markers:
        require(marker in text, f"Production DR Rehearsal missing marker: {marker}")
    require(text.count('ref: ${{ github.sha }}') == 2, "both DR code-consuming jobs must checkout exact Evidence Head")
    require(text.count("fetch-depth: 0") == 2, "both DR checkouts must have full ancestry")
    require(text.count("persist-credentials: false") == 2, "DR checkouts must not persist credentials")
    forbidden = (
        "DR rehearsal workflow HEAD must equal manifest RC SHA",
        'test "$(git rev-parse HEAD)" = "$RC_SHA"',
        "assignPublicIp=ENABLED",
        "--publicly-accessible",
    )
    for marker in forbidden:
        require(marker not in text, f"Production DR Rehearsal retains forbidden V1/unsafe marker: {marker}")


def validate_freeze() -> None:
    text = FREEZE.read_text(encoding="utf-8")
    require_sha_pins(text, "Freeze Production Recovery Evidence")
    markers = (
        "permissions:\n  contents: read",
        "validate-freeze:",
        "contents: read\n      actions: read",
        "commit-freeze:",
        "contents: write",
        'test "$(jq -r \'.name\' <<<"$run")" = "Production DR Rehearsal"',
        'test "$(jq -r \'.path\' <<<"$run")" = ".github/workflows/production-dr-rehearsal.yml"',
        'test "$(jq -r \'.head_branch\' <<<"$run")" = "release-closure-p0"',
        'test "$(jq -r \'.conclusion\' <<<"$run")" = "success"',
        'git merge-base --is-ancestor "$RC_SHA" "$producer_head"',
        'git merge-base --is-ancestor "$producer_head" "$GITHUB_SHA"',
        "production-dr-${{ steps.identity.outputs.deployment_id }}-${{ inputs.dr_run_id }}",
        'cp /tmp/source-run.json "$RECOVERY_DIR/source-run.json"',
        "validate_frozen_production_recovery_evidence.py --self-test",
        '--expected-evidence-head "$GITHUB_SHA"',
        "production-recovery-freeze-${{ github.run_id }}",
        'remote="$(git ls-remote',
        'test "$remote" = "$expected"',
        'HEAD:release-closure-p0',
    )
    for marker in markers:
        require(marker in text, f"Production recovery freeze missing marker: {marker}")
    require("--force" not in text and "git push -f" not in text, "Production recovery freeze must not force push")
    commit_start = text.find("  commit-freeze:\n")
    require(commit_start >= 0, "Production recovery freeze commit job missing")
    commit = text[commit_start:]
    for forbidden in (
        "production-recovery-decision.py",
        "validate_frozen_production_recovery_evidence.py",
        "gh api",
        "aws ",
        "terraform ",
    ):
        require(forbidden not in commit, f"write-capable recovery freeze job must not execute validation/runtime logic: {forbidden}")
    require(text.count('GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}') == 1, "recovery freeze write token must be injected exactly once")


def validate_bundle_and_assembly() -> None:
    module = load_module(FROZEN_VALIDATOR, "lumi_recovery_bundle_contract")
    result: dict[str, Any] = module.self_test()
    require(result.get("status") == "PASS", "frozen recovery provenance self-test did not PASS")
    require(result.get("negative_drills") == 8, "frozen recovery provenance negative drill count drift")
    assembler = ASSEMBLER.read_text(encoding="utf-8")
    markers = (
        "Require canonical frozen Production recovery bundle and producer provenance",
        "python3 scripts/validate_frozen_production_recovery_evidence.py --self-test",
        '--decision "$RECOVERY_DECISION"',
        '--source-run "$recovery_source_run"',
        '--manifest "$PRODUCTION_MANIFEST"',
        '--expected-evidence-head "$GITHUB_SHA"',
    )
    for marker in markers:
        require(marker in assembler, f"Final assembler workflow missing recovery provenance marker: {marker}")
    recovery_pos = assembler.find("Require canonical frozen Production recovery bundle and producer provenance")
    assemble_pos = assembler.find("Assemble only from frozen Source-RC evidence and pre-final policies")
    require(0 <= recovery_pos < assemble_pos, "recovery bundle validation must run before final package assembly")


def validate_policy_membership() -> None:
    policy = json.loads(PINS.read_text(encoding="utf-8"))
    evidence = policy.get("release_evidence_workflows")
    require(isinstance(evidence, list), "release evidence workflow pin list missing")
    required = {
        ".github/workflows/collect-staging-database-parity.yml",
        ".github/workflows/freeze-staging-database-parity.yml",
        ".github/workflows/production-dr-rehearsal.yml",
        ".github/workflows/freeze-production-recovery-evidence.yml",
    }
    require(set(evidence) == required, "P0 release evidence Action-pin workflow set drift")
    critical = policy.get("release_critical_workflows")
    require(isinstance(critical, list) and len(critical) == 9, "release executor registry must remain exactly nine workflows")
    require(required.isdisjoint(set(critical)), "evidence producers must not pollute the nine release executor registry")


def main() -> int:
    for path in (DR, FREEZE, ASSEMBLER, FROZEN_VALIDATOR, PINS):
        require(path.is_file(), f"required recovery workflow source missing: {path.relative_to(ROOT)}")
    validate_dr()
    validate_freeze()
    validate_bundle_and_assembly()
    validate_policy_membership()
    print(
        json.dumps(
            {
                "status": "PASS",
                "v2_source_rc_evidence_head_split": True,
                "private_runtime_recovery": True,
                "freeze_two_phase": True,
                "producer_provenance_negative_drills": 8,
                "final_assembler_bound": True,
                "evidence_workflow_pin_count": 4,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RecoveryWorkflowContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Production recovery evidence workflow contract failed: {exc}") from exc
