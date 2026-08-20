#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
ASSEMBLER_PATH = ROOT / "scripts/final-acceptance-assembler.py"
PACKAGE_VALIDATOR_PATH = ROOT / "scripts/validate_final_acceptance_package.py"
GOVERNANCE_VALIDATOR_PATH = ROOT / "scripts/capture_release_branch_protection.py"
AUTHORIZATION_VALIDATOR_PATH = ROOT / "scripts/capture_release_authorization.py"
FIXTURE_RELEASE_ID = "_node73-assembler-contract"
FIXTURE_ROOT = ROOT / "reports" / "final-acceptance" / FIXTURE_RELEASE_ID
PROD_ROOT = ROOT / "reports" / "production-deployments" / FIXTURE_RELEASE_ID
UPSTREAM_ROOT = ROOT / "reports" / "final-upstream-contract" / FIXTURE_RELEASE_ID
GOVERNANCE_ROOT = ROOT / "reports" / "repository-governance" / FIXTURE_RELEASE_ID


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"final acceptance assembler contract invalid: {message}")


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def clean_dirs() -> None:
    for path in (FIXTURE_ROOT, PROD_ROOT, UPSTREAM_ROOT, GOVERNANCE_ROOT):
        if path.exists():
            shutil.rmtree(path)


def build_authorization_fixture(
    authorization_validator: ModuleType,
    *,
    rc: dict[str, str],
) -> Path:
    source = FIXTURE_ROOT / "source"
    policy_path = source / "approval-policy.json"
    policy = {
        "schema_version": 1,
        "kind": authorization_validator.POLICY_KIND,
        "repository": authorization_validator.EXPECTED_REPOSITORY,
        "pull_request": authorization_validator.EXPECTED_PR,
        "base_ref": authorization_validator.EXPECTED_BASE_REF,
        "head_ref": authorization_validator.EXPECTED_HEAD_REF,
        "minimum_distinct_actors": 3,
        "roles": {
            "product": {"allowed_logins": ["alice"]},
            "engineering": {"allowed_logins": ["bob"]},
            "security": {"allowed_logins": ["carol"]},
            "operations": {"allowed_logins": ["alice", "dave"]},
            "release_owner": {"allowed_logins": ["dave"]},
        },
        "separation_of_duties": [["engineering", "security"], ["security", "release_owner"]],
        "require_human_reviewers": True,
        "require_exact_rc_review_commit": True,
    }
    write(policy_path, policy)

    handoff = {
        "on_call_owner": "platform-on-call",
        "support_owner": "support-owner",
        "incident_commander_rotation": "incident-rotation",
        "first_day_watch_owner": "release-owner",
        "quality_cost_review_owner": "ai-ops-owner",
        "security_dependency_review_owner": "security-owner",
        "dr_drill_owner": "reliability-owner",
        "capacity_review_owner": "platform-owner",
    }
    request_path = source / "authorization-request.json"
    request = {
        "schema_version": 1,
        "kind": authorization_validator.REQUEST_KIND,
        "release_id": FIXTURE_RELEASE_ID,
        "release_candidate": copy.deepcopy(rc),
        "repository": authorization_validator.EXPECTED_REPOSITORY,
        "pull_request": authorization_validator.EXPECTED_PR,
        "approval_policy": authorization_validator._frozen(policy_path),
        "operational_handoff": handoff,
    }
    write(request_path, request)
    normalized_request, normalized_policy_path, normalized_policy = authorization_validator.validate_request(request)

    pr = {
        "number": authorization_validator.EXPECTED_PR,
        "state": "open",
        "html_url": (
            f"https://github.com/{authorization_validator.EXPECTED_REPOSITORY}"
            f"/pull/{authorization_validator.EXPECTED_PR}"
        ),
        "user": {"login": "pr-author"},
        "head": {
            "ref": authorization_validator.EXPECTED_HEAD_REF,
            "sha": rc["git_sha"],
            "repo": {"full_name": authorization_validator.EXPECTED_REPOSITORY},
        },
        "base": {"ref": authorization_validator.EXPECTED_BASE_REF},
    }
    reviews: list[dict[str, Any]] = []
    for index, actor in enumerate(("alice", "bob", "carol", "dave"), start=1):
        reviews.append(
            {
                "id": index,
                "state": "APPROVED",
                "html_url": (
                    f"https://github.com/{authorization_validator.EXPECTED_REPOSITORY}"
                    f"/pull/{authorization_validator.EXPECTED_PR}#pullrequestreview-{index}"
                ),
                "commit_id": rc["git_sha"],
                "submitted_at": f"2026-08-20T00:0{index}:00Z",
                "user": {"login": actor},
            }
        )
    authorization = authorization_validator.build_authorization(
        request_path,
        normalized_request,
        normalized_policy_path,
        normalized_policy,
        pr,
        reviews,
    )
    authorization_path = source / "release-authorization.json"
    write(authorization_path, authorization)
    return authorization_path


def base_fixture(
    assembler: ModuleType,
    governance_validator: ModuleType,
    authorization_validator: ModuleType,
) -> tuple[argparse.Namespace, dict[str, Path], Path, Path]:
    matrix = json.loads((ROOT / "final/acceptance/manifest-v1.json").read_text(encoding="utf-8"))
    require(len(matrix.get("scenarios", [])) == 46, "canonical matrix must contain 46 scenarios")
    rc = {
        "git_sha": "a" * 40,
        "version": "1.0.0-rc.1",
        "migration_head": "0020_generation_operation_identity",
    }
    atom = FIXTURE_ROOT / "source" / "proof.json"
    write(atom, {"schema_version": 1, "passed": True, "kind": "contract-proof"})
    atom_ref = assembler.frozen(atom)

    production = PROD_ROOT / "manifest.json"
    write(
        production,
        {
            "schema_version": 1,
            "deployment_id": FIXTURE_RELEASE_ID,
            "environment": "production",
            "release_candidate": copy.deepcopy(rc),
            "edge": {"domain": "contract.example.invalid"},
        },
    )

    protection_profile = governance_validator._profile_fixture()
    governance = GOVERNANCE_ROOT / "branch-protection.json"
    write(
        governance,
        {
            "schema_version": 1,
            "kind": governance_validator.KIND,
            "status": "PASS",
            "repository": "zhangjaky71-stack/LUMI-AI-DESIGN-OS",
            "branches": [
                {
                    "name": "node-73-final-acceptance-release",
                    "protected": True,
                    "head_sha": "b" * 40,
                    "protection": copy.deepcopy(protection_profile),
                },
                {
                    "name": "release-closure-p0",
                    "protected": True,
                    "head_sha": rc["git_sha"],
                    "protection": copy.deepcopy(protection_profile),
                },
            ],
        },
    )

    upstream_paths: dict[str, Path] = {}
    for name in assembler.UPSTREAM_GATES:
        path = UPSTREAM_ROOT / f"{name}.json"
        write(
            path,
            {
                "schema_version": 1,
                "deployment_id": FIXTURE_RELEASE_ID,
                "release_candidate": copy.deepcopy(rc),
                "decision_id": f"{name}-contract-decision",
                "passed": True,
                "evidence_refs": [copy.deepcopy(atom_ref)],
                "blockers": [],
            },
        )
        upstream_paths[name] = path

    authorization = build_authorization_fixture(authorization_validator, rc=rc)

    scenario_results = FIXTURE_ROOT / "source" / "scenario-results.json"
    write(
        scenario_results,
        {
            "schema_version": 1,
            "release_id": FIXTURE_RELEASE_ID,
            "release_candidate": copy.deepcopy(rc),
            "items": [
                {
                    "id": scenario["id"],
                    "status": "PASS",
                    "evidence_refs": [copy.deepcopy(atom_ref)],
                    "notes": "contract fixture",
                }
                for scenario in matrix["scenarios"]
            ],
        },
    )

    args = argparse.Namespace(
        matrix="final/acceptance/manifest-v1.json",
        release_id=FIXTURE_RELEASE_ID,
        production_manifest=rel(production),
        repository_governance=rel(governance),
        security=rel(upstream_paths["security"]),
        recovery=rel(upstream_paths["recovery"]),
        performance=rel(upstream_paths["performance"]),
        ai_regression=rel(upstream_paths["ai_regression"]),
        staging_acceptance=rel(upstream_paths["staging_acceptance"]),
        production_deployment=rel(upstream_paths["production_deployment"]),
        authorization=rel(authorization),
        scenario_results=rel(scenario_results),
    )
    return args, upstream_paths, authorization, scenario_results


def expect_block(
    assembler: ModuleType,
    governance_validator: ModuleType,
    authorization_validator: ModuleType,
    mutate: Callable[[argparse.Namespace, dict[str, Path], Path, Path], None],
    label: str,
) -> None:
    clean_dirs()
    args, upstream, authorization, scenarios = base_fixture(
        assembler,
        governance_validator,
        authorization_validator,
    )
    mutate(args, upstream, authorization, scenarios)
    try:
        assembler.assemble(args)
    except assembler.AssemblyError:
        return
    raise SystemExit(f"final acceptance assembler contract invalid: {label} must block")


def main() -> int:
    assembler = load_module(ASSEMBLER_PATH, "lumi_final_assembler")
    package = load_module(PACKAGE_VALIDATOR_PATH, "lumi_final_package_validator")
    governance_validator = load_module(GOVERNANCE_VALIDATOR_PATH, "lumi_governance_validator")
    authorization_validator = load_module(AUTHORIZATION_VALIDATOR_PATH, "lumi_authorization_validator")
    clean_dirs()
    try:
        args, upstream, authorization, scenarios = base_fixture(
            assembler,
            governance_validator,
            authorization_validator,
        )
        release_path, evidence_path = assembler.assemble(args)
        require(release_path.name == "release.json", "assembler internal release filename changed unexpectedly")
        canonical_release = release_path.with_name("release-manifest.json")
        release_path.replace(canonical_release)
        validated = package.validate(canonical_release)
        require(validated["status"] == "PASS", "clean assembled package must validate")
        require("repository_governance_sha256" in validated, "clean package must freeze repository governance")
        require("authorization_sha256" in validated, "clean package must freeze provenance-backed authorization")
        require(evidence_path.is_file(), "clean acceptance evidence missing")

        def cross_rc(_args: argparse.Namespace, paths: dict[str, Path], _auth: Path, _scenarios: Path) -> None:
            payload = json.loads(paths["security"].read_text(encoding="utf-8"))
            payload["release_candidate"]["git_sha"] = "b" * 40
            write(paths["security"], payload)

        expect_block(assembler, governance_validator, authorization_validator, cross_rc, "cross-RC Security decision")

        def missing_scenario(_args: argparse.Namespace, _paths: dict[str, Path], _auth: Path, scenarios_path: Path) -> None:
            payload = json.loads(scenarios_path.read_text(encoding="utf-8"))
            payload["items"].pop()
            write(scenarios_path, payload)

        expect_block(assembler, governance_validator, authorization_validator, missing_scenario, "missing scenario")

        def pass_without_evidence(_args: argparse.Namespace, _paths: dict[str, Path], _auth: Path, scenarios_path: Path) -> None:
            payload = json.loads(scenarios_path.read_text(encoding="utf-8"))
            payload["items"][0]["evidence_refs"] = []
            write(scenarios_path, payload)

        expect_block(assembler, governance_validator, authorization_validator, pass_without_evidence, "PASS without evidence")

        def approval_actor_swap(_args: argparse.Namespace, _paths: dict[str, Path], auth_path: Path, _scenarios: Path) -> None:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
            payload["approvals"]["security"]["actor"] = "alice"
            write(auth_path, payload)

        expect_block(assembler, governance_validator, authorization_validator, approval_actor_swap, "authorization actor swap")

        def approval_commit_swap(_args: argparse.Namespace, _paths: dict[str, Path], auth_path: Path, _scenarios: Path) -> None:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
            payload["approvals"]["engineering"]["commit_id"] = "b" * 40
            write(auth_path, payload)

        expect_block(assembler, governance_validator, authorization_validator, approval_commit_swap, "authorization RC commit swap")

        def approval_policy_tamper(_args: argparse.Namespace, _paths: dict[str, Path], auth_path: Path, _scenarios: Path) -> None:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
            policy_path = ROOT / payload["approval_policy"]["path"]
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["minimum_distinct_actors"] = 1
            write(policy_path, policy)

        expect_block(assembler, governance_validator, authorization_validator, approval_policy_tamper, "authorization policy hash tamper")

        def unprotected_branch(args: argparse.Namespace, _paths: dict[str, Path], _auth: Path, _scenarios: Path) -> None:
            path = ROOT / args.repository_governance
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["branches"][1]["protected"] = False
            payload["status"] = "BLOCKED_EXTERNAL"
            write(path, payload)

        expect_block(assembler, governance_validator, authorization_validator, unprotected_branch, "unprotected release branch")

        def governance_repo_swap(args: argparse.Namespace, _paths: dict[str, Path], _auth: Path, _scenarios: Path) -> None:
            path = ROOT / args.repository_governance
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["repository"] = "example/other"
            write(path, payload)

        expect_block(assembler, governance_validator, authorization_validator, governance_repo_swap, "repository governance repo swap")

        def governance_head_swap(args: argparse.Namespace, _paths: dict[str, Path], _auth: Path, _scenarios: Path) -> None:
            path = ROOT / args.repository_governance
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["branches"][1]["head_sha"] = "c" * 40
            write(path, payload)

        expect_block(assembler, governance_validator, authorization_validator, governance_head_swap, "repository governance RC head swap")

        def governance_force_push(args: argparse.Namespace, _paths: dict[str, Path], _auth: Path, _scenarios: Path) -> None:
            path = ROOT / args.repository_governance
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["branches"][0]["protection"]["allow_force_pushes"] = True
            write(path, payload)

        expect_block(assembler, governance_validator, authorization_validator, governance_force_push, "unsafe force-push protection profile")

        print("final acceptance assembler contract: PASS")
        return 0
    finally:
        clean_dirs()


if __name__ == "__main__":
    raise SystemExit(main())
