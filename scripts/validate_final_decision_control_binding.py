#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "scripts" / "final-acceptance-decision.py"
WORKFLOW = ROOT / ".github" / "workflows" / "final-acceptance-gate.yml"


class ControlBindingError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ControlBindingError(message)


def block(text: str, start_marker: str, next_marker: str | None) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise ControlBindingError(f"missing block: {start_marker}")
    if next_marker is None:
        return text[start:]
    end = text.find(next_marker, start + len(start_marker))
    if end < 0:
        raise ControlBindingError(f"missing block terminator: {next_marker}")
    return text[start:end]


def main() -> int:
    decision = DECISION.read_text(encoding="utf-8")
    for marker in (
        'PRODUCT_GATE = ROOT / "scripts" / "final-acceptance-gate.py"',
        'PACKAGE_VALIDATOR = ROOT / "scripts" / "validate_final_acceptance_package.py"',
        'GOVERNANCE = ROOT / "scripts" / "capture_release_branch_protection.py"',
        'AUTHORIZATION = ROOT / "scripts" / "capture_release_authorization.py"',
        'require_token("RELEASE_GOVERNANCE_TOKEN")',
        'governance.capture(EXPECTED_REPOSITORY, token=governance_token)',
        'governance.validate_report(',
        'expected_release_sha=rc_sha',
        'require_token("RELEASE_APPROVAL_TOKEN")',
        'authorization.verify_live_authorization(',
        'product_gate.evaluate(matrix, release, evidence, evidence_path)',
        '"live_release_controls": live_controls',
        '"repository_governance": {',
        '"release_authorization": {',
        '"sha256": sha256(governance_path)',
        '"sha256": sha256(authorization_path)',
        '"canonical_inputs": {',
        '"release_manifest": {',
        '"acceptance_evidence": {',
        '"acceptance_matrix": {',
        'canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))',
        'hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]',
        'if path.name != "final-decision.json"',
    ):
        require(marker in decision, f"canonical final decision missing live-control binding marker: {marker}")

    package_pos = decision.find("package_validator.validate(release_path)")
    governance_pos = decision.find("governance.capture(EXPECTED_REPOSITORY, token=governance_token)")
    authorization_pos = decision.find("authorization.verify_live_authorization(")
    product_pos = decision.find("product_gate.evaluate(matrix, release, evidence, evidence_path)")
    bind_pos = decision.find('"live_release_controls": live_controls')
    decision_id_pos = decision.find('hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]')
    require(
        min(package_pos, governance_pos, authorization_pos, product_pos, bind_pos, decision_id_pos) >= 0
        and package_pos < governance_pos < authorization_pos < product_pos < bind_pos < decision_id_pos,
        "canonical final decision order must be package -> live governance -> live authorization -> product gate -> evidence binding -> decision id",
    )

    workflow = WORKFLOW.read_text(encoding="utf-8")
    final = block(workflow, "  final-decision:\n", "  contract-gate:\n")
    for marker in (
        "permissions:\n      contents: read\n      pull-requests: read\n",
        "name: Require canonical assembled and frozen package",
        "name: Evaluate canonical final decision with live release controls",
        'RELEASE_GOVERNANCE_TOKEN: ${{ secrets.RELEASE_GOVERNANCE_TOKEN }}',
        'RELEASE_APPROVAL_TOKEN: ${{ secrets.GITHUB_TOKEN }}',
        "python3 scripts/final-acceptance-decision.py",
        '--release "$FINAL_RELEASE"',
        '--evidence "$FINAL_EVIDENCE"',
        '--output "$FINAL_OUTPUT"',
        "path: reports/final-acceptance/**",
    ):
        require(marker in final, f"Final Acceptance workflow missing canonical decision marker: {marker}")

    package_step_pos = final.find("name: Require canonical assembled and frozen package")
    decision_step_pos = final.find("name: Evaluate canonical final decision with live release controls")
    archive_pos = final.find("actions/upload-artifact@")
    require(
        min(package_step_pos, decision_step_pos, archive_pos) >= 0
        and package_step_pos < decision_step_pos < archive_pos,
        "Final Acceptance workflow must validate package, run canonical live-control decision, then archive",
    )
    require(
        "python3 scripts/final-acceptance-gate.py" not in final,
        "Final Acceptance final-decision job must not bypass the live-control wrapper by invoking product gate directly",
    )

    print("NODE-73 final decision live-control artifact binding contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ControlBindingError, OSError) as exc:
        raise SystemExit(f"final decision control binding contract failed: {exc}") from exc
