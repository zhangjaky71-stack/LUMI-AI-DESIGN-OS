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
ASSEMBLER_PATH = ROOT / "scripts" / "final-acceptance-assembler-v2.py"
PACKAGE_PATH = ROOT / "scripts" / "validate_final_acceptance_package_v2.py"
AUTH_PATH = ROOT / "scripts" / "capture_release_authorization_v2.py"
FIXTURE_ID = "_node73-v2-contract"
FIXTURE_ROOT = ROOT / "reports" / "final-acceptance" / FIXTURE_ID
PROD_ROOT = ROOT / "reports" / "production-deployments" / FIXTURE_ID
UPSTREAM_ROOT = ROOT / "reports" / "final-upstream-contract-v2" / FIXTURE_ID


class V2PackageContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise V2PackageContractError(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise V2PackageContractError(f"unable to import {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def clean() -> None:
    for path in (FIXTURE_ROOT, PROD_ROOT, UPSTREAM_ROOT):
        if path.exists():
            shutil.rmtree(path)


def fixture(assembler: ModuleType, auth: ModuleType) -> tuple[argparse.Namespace, dict[str, Path]]:
    matrix = json.loads((ROOT / "final/acceptance/manifest-v1.json").read_text(encoding="utf-8"))
    require(len(matrix.get("scenarios", [])) == 46, "canonical matrix must contain 46 scenarios")
    rc = {"git_sha": "a" * 40, "version": "1.0.0-rc.1", "migration_head": "0020_generation_operation_identity"}
    proof = FIXTURE_ROOT / "source" / "proof.json"
    write(proof, {"schema_version": 1, "kind": "V2-CONTRACT-PROOF", "passed": True})
    proof_ref = assembler.frozen(proof)

    production = PROD_ROOT / "manifest.json"
    write(production, {
        "schema_version": 1,
        "deployment_id": FIXTURE_ID,
        "environment": "production",
        "release_candidate": copy.deepcopy(rc),
        "edge": {"domain": "contract.example.invalid"},
    })

    policy = FIXTURE_ROOT / "source" / "approval-policy-v2.json"
    write(policy, {
        "schema_version": 2,
        "kind": auth.POLICY_KIND,
        "repository": auth.EXPECTED_REPOSITORY,
        "pull_request": auth.EXPECTED_PR,
        "base_ref": auth.EXPECTED_BASE_REF,
        "head_ref": auth.EXPECTED_HEAD_REF,
        "minimum_distinct_actors": 3,
        "roles": {
            "product": {"allowed_logins": ["alice"]},
            "engineering": {"allowed_logins": ["bob"]},
            "security": {"allowed_logins": ["carol"]},
            "operations": {"allowed_logins": ["alice", "dave"]},
            "release_owner": {"allowed_logins": ["dave"]}
        },
        "separation_of_duties": [["engineering", "security"], ["security", "release_owner"]],
        "require_human_reviewers": True,
        "require_exact_evidence_head_review_commit": True,
        "require_pr_author_exclusion": True,
        "require_latest_decisive_review": True,
    })

    authorization_request = FIXTURE_ROOT / "source" / "authorization-request-v2.json"
    write(authorization_request, {
        "schema_version": 2,
        "kind": auth.REQUEST_KIND,
        "release_id": FIXTURE_ID,
        "source_release_candidate": copy.deepcopy(rc),
        "repository": auth.EXPECTED_REPOSITORY,
        "pull_request": auth.EXPECTED_PR,
        "approval_policy": assembler.frozen(policy),
        "operational_handoff": {
            "on_call_owner": "platform-on-call",
            "support_owner": "support-owner",
            "incident_commander_rotation": "incident-rotation",
            "first_day_watch_owner": "release-owner",
            "quality_cost_review_owner": "ai-ops-owner",
            "security_dependency_review_owner": "security-owner",
            "dr_drill_owner": "reliability-owner",
            "capacity_review_owner": "platform-owner"
        },
    })

    upstream: dict[str, Path] = {}
    for name in assembler.UPSTREAM_GATES:
        path = UPSTREAM_ROOT / f"{name}.json"
        write(path, {
            "schema_version": 1,
            "deployment_id": FIXTURE_ID,
            "release_candidate": copy.deepcopy(rc),
            "decision_id": f"{name}-v2-contract",
            "passed": True,
            "evidence_refs": [copy.deepcopy(proof_ref)],
            "blockers": [],
        })
        upstream[name] = path

    scenarios = FIXTURE_ROOT / "source" / "scenario-results.json"
    write(scenarios, {
        "schema_version": 1,
        "release_id": FIXTURE_ID,
        "release_candidate": copy.deepcopy(rc),
        "items": [{"id": scenario["id"], "status": "PASS", "evidence_refs": [copy.deepcopy(proof_ref)], "notes": "V2 contract fixture"} for scenario in matrix["scenarios"]],
    })

    args = argparse.Namespace(
        matrix="final/acceptance/manifest-v1.json",
        release_id=FIXTURE_ID,
        production_manifest=rel(production),
        governance_policy="final/acceptance/repository-governance-policy-template.json",
        authorization_request=rel(authorization_request),
        security=rel(upstream["security"]),
        recovery=rel(upstream["recovery"]),
        performance=rel(upstream["performance"]),
        ai_regression=rel(upstream["ai_regression"]),
        staging_acceptance=rel(upstream["staging_acceptance"]),
        production_deployment=rel(upstream["production_deployment"]),
        scenario_results=rel(scenarios),
    )
    return args, {
        "policy": policy,
        "authorization_request": authorization_request,
        "scenarios": scenarios,
        **upstream,
    }


def expect_assembly_block(assembler: ModuleType, auth: ModuleType, mutate: Callable[[argparse.Namespace, dict[str, Path]], None], label: str) -> None:
    clean()
    args, paths = fixture(assembler, auth)
    mutate(args, paths)
    try:
        assembler.assemble(args)
    except assembler.AssemblyV2Error:
        return
    raise V2PackageContractError(f"{label} must block V2 assembly")


def main() -> int:
    assembler = load_module(ASSEMBLER_PATH, "lumi_v2_assembler_contract")
    package = load_module(PACKAGE_PATH, "lumi_v2_package_contract")
    auth = load_module(AUTH_PATH, "lumi_v2_auth_contract_fixture")
    clean()
    try:
        args, paths = fixture(assembler, auth)
        release_path, evidence_path = assembler.assemble(args)
        require(release_path.name == "release-manifest-v2.json", "V2 assembler output filename mismatch")
        result = package.validate(release_path)
        require(result.get("status") == "PASS", "clean V2 package must validate")
        require(result.get("approvals_state") == "PENDING_LIVE_AUTHORIZATION", "clean V2 package must remain pending live authorization")
        release = json.loads(release_path.read_text(encoding="utf-8"))
        require(all(value == "PENDING" for value in release["approvals"].values()), "clean committed package must not contain pre-approved statuses")
        require("release_authorization" not in release and "repository_governance" not in release, "clean committed V2 package must not contain live reports")
        require(evidence_path.is_file(), "V2 acceptance evidence missing")

        preapproved = copy.deepcopy(release)
        preapproved["approvals"]["security"] = "APPROVED"
        write(release_path, preapproved)
        try:
            package.validate(release_path)
        except package.PackageV2Error:
            pass
        else:
            raise V2PackageContractError("pre-approved committed package must block")

        write(release_path, release)
        live_injected = copy.deepcopy(release)
        live_injected["release_authorization"] = {"path": "reports/fake.json", "sha256": "0" * 64}
        write(release_path, live_injected)
        try:
            package.validate(release_path)
        except package.PackageV2Error:
            pass
        else:
            raise V2PackageContractError("live authorization injected into committed package must block")

        def source_swap(_args: argparse.Namespace, fixture_paths: dict[str, Path]) -> None:
            payload = json.loads(fixture_paths["authorization_request"].read_text(encoding="utf-8"))
            payload["source_release_candidate"]["git_sha"] = "b" * 40
            write(fixture_paths["authorization_request"], payload)
        expect_assembly_block(assembler, auth, source_swap, "authorization Source RC swap")

        def policy_hash_tamper(_args: argparse.Namespace, fixture_paths: dict[str, Path]) -> None:
            payload = json.loads(fixture_paths["authorization_request"].read_text(encoding="utf-8"))
            payload["approval_policy"]["sha256"] = "0" * 64
            write(fixture_paths["authorization_request"], payload)
        expect_assembly_block(assembler, auth, policy_hash_tamper, "approval policy hash tamper")

        def upstream_swap(_args: argparse.Namespace, fixture_paths: dict[str, Path]) -> None:
            payload = json.loads(fixture_paths["security"].read_text(encoding="utf-8"))
            payload["release_candidate"]["git_sha"] = "b" * 40
            write(fixture_paths["security"], payload)
        expect_assembly_block(assembler, auth, upstream_swap, "upstream Source RC swap")

        def missing_scenario(_args: argparse.Namespace, fixture_paths: dict[str, Path]) -> None:
            payload = json.loads(fixture_paths["scenarios"].read_text(encoding="utf-8"))
            payload["items"].pop()
            write(fixture_paths["scenarios"], payload)
        expect_assembly_block(assembler, auth, missing_scenario, "missing scenario")

        print(json.dumps({"status": "PASS", "negative_drills": 6, "scenario_count": 46}, sort_keys=True))
        return 0
    finally:
        clean()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (V2PackageContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"final acceptance V2 package contract failed: {exc}") from exc
