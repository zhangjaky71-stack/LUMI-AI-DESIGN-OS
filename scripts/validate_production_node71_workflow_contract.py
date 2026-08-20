#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"
MANIFEST = ROOT / "production" / "deployment" / "manifest-template.json"
CANONICAL_PATH = "reports/production-deployments/runtime/node71/decision.json"
DOWNLOAD_ACTION = "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1"


class WorkflowContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowContractError(message)


def _job_block(text: str, job_name: str, next_job: str | None) -> str:
    marker = f"  {job_name}:\n"
    start = text.find(marker)
    if start < 0:
        raise WorkflowContractError(f"missing workflow job: {job_name}")
    if next_job is None:
        return text[start:]
    end = text.find(f"  {next_job}:\n", start + len(marker))
    if end < 0:
        raise WorkflowContractError(f"missing workflow job terminator: {next_job}")
    return text[start:end]


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    manifest_text = MANIFEST.read_text(encoding="utf-8")

    require("acceptance_decision_path:" not in text, "manual NODE-71 decision path input must remain removed")
    for marker in (
        "staging_acceptance_run_id:",
        'description: "Exact Staging Acceptance Gate run id that produced the NODE-71 decision artifact"',
        "actions: read",
        "STAGING_ACCEPTANCE_RUN_ID: ${{ inputs.staging_acceptance_run_id }}",
        DOWNLOAD_ACTION,
        "name: staging-acceptance-decision",
        "github-token: ${{ secrets.GITHUB_TOKEN }}",
        "repository: ${{ github.repository }}",
        "run-id: ${{ inputs.staging_acceptance_run_id }}",
        "scripts/validate_node71_decision_artifact.py",
        "python3 scripts/validate_release_action_pins.py",
        '--acceptance-provenance "$ACCEPTANCE_PROVENANCE_PATH"',
        '--acceptance-run-id "$STAGING_ACCEPTANCE_RUN_ID"',
        '--repository "${{ github.repository }}"',
        CANONICAL_PATH,
    ):
        require(marker in text, f"production workflow missing NODE-71 binding marker: {marker}")

    release = _job_block(text, "release-gate", "production")
    require(
        "production manifest staging_acceptance_run_id differs from requested run id" in release,
        "release-gate must bind manifest NODE-71 run id to requested run",
    )
    require(
        "production manifest staging_acceptance_path must use canonical downloaded NODE-71 path" in release,
        "release-gate must reject manual/stale decision paths",
    )
    require(
        "test -f \"$ACCEPTANCE_PATH\"" in release
        and "test -f \"$ACCEPTANCE_PROVENANCE_PATH\"" in release,
        "release-gate must require decision/provenance pair",
    )
    require(
        "validate_release_action_pins.py" in release,
        "release-gate must fail closed on release action supply-chain drift",
    )

    pin_pos = release.find("validate_release_action_pins.py")
    download_pos = release.find(DOWNLOAD_ACTION)
    provenance_pos = release.find("validate_node71_decision_artifact.py")
    deployment_gate_pos = release.find("production-deployment-gate.py")
    export_pos = release.find("Export immutable release metadata")
    require(
        pin_pos >= 0
        and download_pos >= 0
        and provenance_pos >= 0
        and deployment_gate_pos >= 0
        and export_pos >= 0
        and pin_pos < download_pos < provenance_pos < deployment_gate_pos < export_pos,
        "action pin gate and NODE-71 artifact/provenance/deployment gates must precede release metadata export",
    )

    require(
        '"staging_acceptance_run_id": "PENDING"' in manifest_text,
        "production manifest must require explicit NODE-71 run id",
    )
    require(
        f'"staging_acceptance_path": "{CANONICAL_PATH}"' in manifest_text,
        "production manifest must fix the canonical downloaded NODE-71 path",
    )

    print("NODE-72 exact NODE-71 decision artifact workflow contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WorkflowContractError as exc:
        raise SystemExit(f"production NODE-71 workflow contract failed: {exc}") from exc
