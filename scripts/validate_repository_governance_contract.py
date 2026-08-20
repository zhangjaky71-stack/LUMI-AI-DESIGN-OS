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
    require(result.get("negative_drills") == 4, "branch-protection collector negative drill count drift")

    template = json.loads(RELEASE_TEMPLATE.read_text(encoding="utf-8"))
    governance = template.get("repository_governance")
    require(
        isinstance(governance, dict) and set(governance) == {"path", "sha256"},
        "release manifest template must freeze repository_governance with path + sha256",
    )
    require(governance.get("path") == "PENDING", "repository_governance.path template must start PENDING")
    require(governance.get("sha256") == "PENDING", "repository_governance.sha256 template must start PENDING")

    require_markers(
        ASSEMBLER,
        (
            'parser.add_argument("--repository-governance", required=True)',
            'prefixes=("reports/repository-governance/",)',
            'REPOSITORY_GOVERNANCE_KIND = "LUMI_RELEASE_BRANCH_PROTECTION_V1"',
            'REQUIRED_RELEASE_BRANCHES = {',
            '"node-73-final-acceptance-release"',
            '"release-closure-p0"',
            'item.get("protected") is not True',
            '"repository_governance": repository_governance',
            'by_name[RELEASE_HEAD_BRANCH]["head_sha"].lower() != expected_release_sha.lower()',
        ),
    )
    require_markers(
        PACKAGE_VALIDATOR,
        (
            'REPOSITORY_GOVERNANCE_KIND = "LUMI_RELEASE_BRANCH_PROTECTION_V1"',
            'validate_repository_governance(',
            'release.get("repository_governance")',
            'item.get("protected") is not True',
            'by_name[RELEASE_HEAD_BRANCH]["head_sha"].lower() != expected_release_sha.lower()',
            '"repository_governance_sha256": digest(governance_path)',
        ),
    )
    require_markers(
        ASSEMBLER_CONTRACT,
        (
            'GOVERNANCE_ROOT = ROOT / "reports" / "repository-governance"',
            'repository_governance=rel(governance)',
            'expect_block(assembler, unprotected_branch, "unprotected release branch")',
            'expect_block(assembler, governance_repo_swap, "repository governance repo swap")',
            'expect_block(assembler, governance_head_swap, "repository governance RC head swap")',
        ),
    )

    print("NODE-73 repository governance source contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GovernanceContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"repository governance contract failed: {exc}") from exc
