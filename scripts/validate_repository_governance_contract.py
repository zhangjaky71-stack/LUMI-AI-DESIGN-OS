#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "scripts" / "capture_release_branch_protection.py"
ASSEMBLER = ROOT / "scripts" / "final-acceptance-assembler.py"
PACKAGE_VALIDATOR = ROOT / "scripts" / "validate_final_acceptance_package.py"
ASSEMBLER_CONTRACT = ROOT / "scripts" / "validate_final_acceptance_assembler_contract.py"
FINAL_DECISION = ROOT / "scripts" / "final-acceptance-decision.py"
FINAL_WORKFLOW = ROOT / ".github" / "workflows" / "final-acceptance-gate.yml"
RELEASE_TEMPLATE = ROOT / "final" / "acceptance" / "release-manifest-template.json"


class GovernanceContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GovernanceContractError(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GovernanceContractError(f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_markers(path: Path, markers: tuple[str, ...]) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in markers:
        require(marker in text, f"{path.relative_to(ROOT)} missing repository-governance marker: {marker}")


def main() -> int:
    collector = load_module(COLLECTOR, "lumi_release_branch_protection")
    result: dict[str, Any] = collector.self_test()
    require(result.get("status") == "PASS", "branch-protection collector self-test did not PASS")
    require(result.get("negative_drills") == 11, "strong branch-protection negative drill count drift")

    template = json.loads(RELEASE_TEMPLATE.read_text(encoding="utf-8"))
    governance = template.get("repository_governance")
    require(isinstance(governance, dict) and set(governance) == {"path", "sha256"}, "release manifest must freeze repository governance")
    require(governance.get("path") == "PENDING" and governance.get("sha256") == "PENDING", "governance template must start fail-closed")

    require_markers(COLLECTOR, (
        'PROFILE = "LUMI_RELEASE_PROTECTION_PROFILE_V1"',
        'f"https://api.github.com/repos/{repository}/branches/{branch}/protection"',
        '"detailed branch protection capture requires an Administration-read GitHub token"',
        'status_checks.get("strict") is True',
        'enforce_admins.get("enabled") is True',
        'reviews.get("dismiss_stale_reviews") is True',
        'reviews.get("require_last_push_approval") is True',
        'bypass_count == 0',
        '_enabled(payload, "required_linear_history")',
        '_enabled(payload, "required_conversation_resolution")',
        '_disabled(payload, "allow_force_pushes")',
        '_disabled(payload, "allow_deletions")',
    ))
    require_markers(ASSEMBLER, (
        'parser.add_argument("--repository-governance", required=True)',
        'GOVERNANCE_VALIDATOR = ROOT / "scripts" / "capture_release_branch_protection.py"',
        'validator.validate_report(',
        'expected_release_sha=expected_release_sha',
        '"repository_governance": repository_governance',
    ))
    require_markers(PACKAGE_VALIDATOR, (
        'GOVERNANCE_VALIDATOR = ROOT / "scripts" / "capture_release_branch_protection.py"',
        'release.get("repository_governance")',
        'validator.validate_report(',
        '"repository_governance_sha256": digest(governance_path)',
    ))
    require_markers(ASSEMBLER_CONTRACT, (
        'protection_profile = governance_validator._profile_fixture()',
        'unprotected release branch',
        'repository governance repo swap',
        'repository governance RC head swap',
        'unsafe force-push protection profile',
    ))

    require_markers(FINAL_DECISION, (
        'GOVERNANCE = ROOT / "scripts" / "capture_release_branch_protection.py"',
        'require_token("RELEASE_GOVERNANCE_TOKEN")',
        'governance.capture(EXPECTED_REPOSITORY, token=governance_token)',
        'governance.validate_report(',
        'expected_release_sha=rc_sha',
        'runtime_dir / "repository-governance-live.json"',
        '"repository_governance": {',
        '"sha256": sha256(governance_path)',
        '"protection_profile": governance_result.get("protection_profile")',
        '"release_head_sha": governance_result.get("release_head_sha")',
    ))

    workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
    for marker in (
        'name: Evaluate canonical final decision with live release controls',
        'RELEASE_GOVERNANCE_TOKEN: ${{ secrets.RELEASE_GOVERNANCE_TOKEN }}',
        'python3 scripts/final-acceptance-decision.py',
    ):
        require(marker in workflow, f"Final Acceptance workflow missing governance wrapper marker: {marker}")
    package_pos = workflow.find("name: Require canonical assembled and frozen package")
    wrapper_pos = workflow.find("name: Evaluate canonical final decision with live release controls")
    require(package_pos >= 0 and wrapper_pos > package_pos, "Final Decision must validate frozen package before canonical live-control wrapper")

    print("NODE-73 strong live repository governance source contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GovernanceContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"repository governance contract failed: {exc}") from exc
