#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "assemble-final-acceptance.yml"
PINS = ROOT / "production" / "release-actions" / "pins-v1.json"
RECOVERY_CONTRACT = ROOT / "scripts" / "validate_production_recovery_evidence_workflow_contract.py"


class AssemblerWorkflowV2Error(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssemblerWorkflowV2Error(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    source = WORKFLOW.read_text(encoding="utf-8")
    required = (
        "authorization_request:",
        'AUTHORIZATION_REQUEST: ${{ inputs.authorization_request }}',
        "GOVERNANCE_POLICY: final/acceptance/repository-governance-policy-template.json",
        "if: github.ref == 'refs/heads/release-closure-p0'",
        'ref: ${{ github.sha }}',
        "fetch-depth: 0",
        'test "$remote_sha" = "$GITHUB_SHA"',
        "python3 scripts/validate_finalization_v2_contract.py",
        "Require canonical frozen Production recovery bundle and producer provenance",
        "python3 scripts/validate_frozen_production_recovery_evidence.py --self-test",
        '--decision "$RECOVERY_DECISION"',
        '--expected-evidence-head "$GITHUB_SHA"',
        "python3 scripts/final-acceptance-assembler-v2.py",
        '--governance-policy "$GOVERNANCE_POLICY"',
        '--authorization-request "$AUTHORIZATION_REQUEST"',
        'release-manifest-v2.json',
        "python3 scripts/validate_final_acceptance_package_v2.py",
        "committed V2 package must keep every approval PENDING",
        "committed V2 package must not contain live release-control reports",
        'git push origin "HEAD:${GITHUB_REF_NAME}"',
    )
    for marker in required:
        require(marker in source, f"final package assembler workflow missing V2 marker: {marker}")
    forbidden = (
        "inputs.authorization }}",
        "final-acceptance-assembler.py",
        "validate_final_acceptance_package.py",
        "release-manifest.json",
        "--authorization ",
        "git push --force",
    )
    for marker in forbidden:
        require(marker not in source, f"final package assembler workflow retains forbidden V1/unsafe marker: {marker}")

    policy = json.loads(PINS.read_text(encoding="utf-8"))
    workflows = policy.get("release_critical_workflows")
    require(isinstance(workflows, list), "release action pin workflow list missing")
    require(
        ".github/workflows/assemble-final-acceptance.yml" in workflows,
        "final package assembler must be covered by release Action pin policy",
    )
    require(
        "permissions:\n  contents: read\n" in source,
        "final package assembler workflow must default to contents:read",
    )
    require(
        "permissions:\n      contents: write\n" in source,
        "final package assembler write permission must be scoped to assemble job",
    )

    recovery = load_module(RECOVERY_CONTRACT, "lumi_v2_recovery_evidence_workflow_contract")
    require(recovery.main() == 0, "Production recovery evidence workflow contract did not PASS")

    print("NODE-73 V2 final package assembler + Production recovery evidence workflow contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssemblerWorkflowV2Error, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"final package assembler V2 workflow contract failed: {exc}") from exc
