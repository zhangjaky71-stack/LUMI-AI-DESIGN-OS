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
    require(
        isinstance(governance, dict) and set(governance) == {"path", "sha256"},
        "release manifest template must freeze repository_governance with path + sha256",
    )
    require(governance.get("path") == "PENDING", "repository_governance.path template must start PENDING")
    require(governance.get("sha256") == "PENDING", "repository_governance.sha256 template must start PENDING")

    require_markers(
        COLLECTOR,
        (
            'PROFILE = "LUMI_RELEASE_PROTECTION_PROFILE_V1"',
            'f"https://api.github.com/repos/{repository}/branches/{branch}/protection"',
            '"detailed branch protection capture requires an Administration-read GitHub token"',
            'status_checks.get("strict") is True',
            '"at least one required status check is mandatory"',
            'enforce_admins.get("enabled") is True',
            'reviews.get("dismiss_stale_reviews") is True',
            'reviews.get("require_last_push_approval") is True',
            'bypass_count == 0',
            '_enabled(payload, "required_linear_history")',
            '_enabled(payload, "required_conversation_resolution")',
            '_disabled(payload, "allow_force_pushes")',
            '_disabled(payload, "allow_deletions")',
            'os.environ.get("RELEASE_GOVERNANCE_TOKEN")',
            'parser.add_argument("--expected-release-sha")',
        ),
    )
    require_markers(
        ASSEMBLER,
        (
            'parser.add_argument("--repository-governance", required=True)',
            'prefixes=("reports/repository-governance/",)',
            'GOVERNANCE_VALIDATOR = ROOT / "scripts" / "capture_release_branch_protection.py"',
            'validator.validate_report(',
            'expected_repository=EXPECTED_REPOSITORY',
            'expected_release_sha=expected_release_sha',
            '"repository_governance": repository_governance',
        ),
    )
    require_markers(
        PACKAGE_VALIDATOR,
        (
            'GOVERNANCE_VALIDATOR = ROOT / "scripts" / "capture_release_branch_protection.py"',
            'validate_repository_governance(',
            'release.get("repository_governance")',
            'validator.validate_report(',
            'expected_repository=EXPECTED_REPOSITORY',
            'expected_release_sha=expected_release_sha',
            '"repository_governance_sha256": digest(governance_path)',
        ),
    )
    require_markers(
        ASSEMBLER_CONTRACT,
        (
            'GOVERNANCE_ROOT = ROOT / "reports" / "repository-governance"',
            'GOVERNANCE_VALIDATOR_PATH = ROOT / "scripts/capture_release_branch_protection.py"',
            'protection_profile = governance_validator._profile_fixture()',
            'repository_governance=rel(governance)',
            'expect_block(assembler, governance_validator, unprotected_branch, "unprotected release branch")',
            'expect_block(assembler, governance_validator, governance_repo_swap, "repository governance repo swap")',
            'expect_block(assembler, governance_validator, governance_head_swap, "repository governance RC head swap")',
            'expect_block(assembler, governance_validator, governance_force_push, "unsafe force-push protection profile")',
        ),
    )
    require_markers(
        FINAL_WORKFLOW,
        (
            'RELEASE_GOVERNANCE_TOKEN: ${{ secrets.RELEASE_GOVERNANCE_TOKEN }}',
            'name: Re-verify live strong repository governance for frozen RC',
            'test -n "$RELEASE_GOVERNANCE_TOKEN"',
            'python3 scripts/capture_release_branch_protection.py',
            '--repository "$GITHUB_REPOSITORY"',
            '--expected-release-sha "$rc_sha"',
            '--output reports/final-acceptance/runtime/repository-governance-live.json',
            'reports/final-acceptance/runtime/repository-governance-live.json',
        ),
    )
    workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
    package_pos = workflow.find("name: Require canonical assembled and frozen package")
    live_pos = workflow.find("name: Re-verify live strong repository governance for frozen RC")
    decision_pos = workflow.find("name: Evaluate final product acceptance")
    require(
        min(package_pos, live_pos, decision_pos) >= 0 and package_pos < live_pos < decision_pos,
        "Final Decision must validate frozen package, then live governance, then evaluate product acceptance",
    )

    print("NODE-73 strong live repository governance source contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GovernanceContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"repository governance contract failed: {exc}") from exc
