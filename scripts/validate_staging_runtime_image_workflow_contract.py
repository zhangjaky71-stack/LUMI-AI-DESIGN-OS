#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "staging-acceptance-gate.yml"
DOWNLOAD_ACTION = "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1"
UPLOAD_ACTION = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2"


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
    end_marker = f"  {next_job}:\n"
    end = text.find(end_marker, start + len(marker))
    if end < 0:
        raise WorkflowContractError(f"missing workflow job terminator: {next_job}")
    return text[start:end]


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    for marker in (
        "runtime_image_set_run_id:",
        'description: "GitHub Actions run id that produced the frozen six-runtime RC image set"',
        "python3 scripts/validate_staging_runtime_image_binding.py --self-test",
        "python3 scripts/validate_staging_runtime_image_workflow_contract.py",
        "python3 scripts/validate_node71_decision_artifact.py --self-test",
        "python3 scripts/validate_release_action_pins.py",
        "scripts/validate_staging_runtime_image_binding.py",
        "scripts/validate_staging_runtime_image_workflow_contract.py",
        "scripts/validate_node71_decision_artifact.py",
        DOWNLOAD_ACTION,
        UPLOAD_ACTION,
        "github-token: ${{ secrets.GITHUB_TOKEN }}",
        "repository: ${{ github.repository }}",
        "run-id: ${{ inputs.runtime_image_set_run_id }}",
        "runtime-image-set-${{ steps.runtime_image_binding.outputs.rc_sha }}",
        "--expected-run-id \"$LUMI_RUNTIME_IMAGE_SET_RUN_ID\"",
        "--write-provenance reports/staging-acceptance/runtime/decision-provenance.json",
        '--expected-run-id "${{ github.run_id }}"',
        '--expected-repository "${{ github.repository }}"',
    ):
        require(marker in text, f"staging workflow missing runtime-image/decision binding marker: {marker}")

    header = text[: text.find("jobs:\n")]
    require(
        "permissions:\n  contents: read\n" in header,
        "NODE-71 workflow must default to contents:read only",
    )
    for forbidden in ("actions: read", "id-token: write", "contents: write", "actions: write", "packages: write", "attestations: write"):
        require(forbidden not in header, f"NODE-71 top-level permission is too broad: {forbidden}")

    source = _job_block(text, "source-contract", "canonical-lock-gate")
    lock_gate = _job_block(text, "canonical-lock-gate", "remote-read-only-preflight")
    preflight = _job_block(text, "remote-read-only-preflight", "acceptance-decision")
    acceptance = _job_block(text, "acceptance-decision", "contract-gate")
    for label, block in (("source-contract", source), ("canonical-lock-gate", lock_gate), ("remote-read-only-preflight", preflight)):
        require("actions: read" not in block, f"NODE-71 {label} must not receive cross-run Actions read permission")
    require(
        "permissions:\n      contents: read\n      actions: read\n" in acceptance,
        "NODE-71 acceptance-decision must be the only job with actions:read",
    )

    require(
        "inputs.runtime_image_set_run_id != ''" in acceptance,
        "acceptance-decision must require runtime_image_set_run_id",
    )
    require(
        "LUMI_RUNTIME_IMAGE_SET_RUN_ID: ${{ inputs.runtime_image_set_run_id }}" in acceptance,
        "acceptance-decision must bind the requested runtime-image build run id",
    )
    require(
        "runtime_image_set_run_id must be a positive decimal GitHub Actions run id" in acceptance,
        "acceptance-decision must validate the run id before artifact download",
    )
    require(
        "artifact_name = f'runtime-image-set-{rc_sha}'" in acceptance,
        "artifact name must be derived from the evidence RC SHA",
    )
    require(
        "fh.write(f'artifact_name={artifact_name}\\n')" in acceptance,
        "derived artifact name must be exported as a step output",
    )
    require(
        "test \"$(find \"$RUNTIME_IMAGE_SET_DIR\" -maxdepth 1 -type f -name 'container-image-set.json' | wc -l)\" -eq 1" in acceptance,
        "downloaded runtime image artifact must contain exactly one top-level container-image-set.json",
    )

    download_pos = acceptance.find(DOWNLOAD_ACTION)
    binding_pos = acceptance.find("validate_staging_runtime_image_binding.py")
    gate_pos = acceptance.find("staging-acceptance-gate.py")
    provenance_pos = acceptance.find("--write-provenance reports/staging-acceptance/runtime/decision-provenance.json")
    self_verify_pos = acceptance.find("Self-verify NODE-71 decision provenance before archive")
    upload_pos = acceptance.find(UPLOAD_ACTION)
    require(
        download_pos >= 0 and binding_pos >= 0 and gate_pos >= 0 and download_pos < binding_pos < gate_pos,
        "exact runtime-image artifact download and binding must run before NODE-71 decision",
    )
    require(
        gate_pos < provenance_pos < self_verify_pos < upload_pos,
        "NODE-71 decision provenance capture/self-verification must occur after decision and before archive",
    )

    require(
        "validate_staging_runtime_image_binding.py --self-test" in source,
        "source-contract must execute runtime image binding negative drills",
    )
    require(
        "validate_staging_runtime_image_workflow_contract.py" in source,
        "source-contract must execute this workflow anti-regression contract",
    )
    require(
        "validate_node71_decision_artifact.py --self-test" in source,
        "source-contract must execute NODE-71 decision artifact negative drills",
    )
    require(
        "validate_release_action_pins.py" in source,
        "source-contract must fail closed on release action supply-chain drift",
    )

    print("NODE-71 frozen runtime-image, decision artifact, and scoped permission workflow contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WorkflowContractError as exc:
        raise SystemExit(f"staging runtime image workflow contract failed: {exc}") from exc
