#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "assemble-final-acceptance.yml"
PINS = ROOT / "production" / "release-actions" / "pins-v1.json"


class AssemblerWorkflowV2Error(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssemblerWorkflowV2Error(message)


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

    print("NODE-73 V2 final package assembler workflow contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssemblerWorkflowV2Error, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"final package assembler V2 workflow contract failed: {exc}") from exc
