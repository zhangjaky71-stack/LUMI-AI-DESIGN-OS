#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSEMBLER_V2 = ROOT / "scripts" / "final-acceptance-assembler-v2.py"
AUTHORIZATION_V2 = ROOT / "scripts" / "capture_release_authorization_v2.py"
FEASIBILITY_V2 = ROOT / "scripts" / "validate_release_approval_policy_feasibility_v2.py"
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
ROLE_INPUTS = {
    "product": "product_logins",
    "engineering": "engineering_logins",
    "security": "security_logins",
    "operations": "operations_logins",
    "release_owner": "release_owner_logins",
}
HANDOFF_KEYS = (
    "on_call_owner",
    "support_owner",
    "incident_commander_rotation",
    "first_day_watch_owner",
    "quality_cost_review_owner",
    "security_dependency_review_owner",
    "dr_drill_owner",
    "capacity_review_owner",
)


class AuthorizationPreparationV2Error(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationPreparationV2Error(message)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AuthorizationPreparationV2Error(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_logins(raw: str, *, label: str) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    require(bool(values), f"{label} must contain at least one GitHub login")
    require(len(values) == len(set(values)), f"{label} contains duplicate GitHub logins")
    return values


def repo_file(raw: str, *, prefix: str) -> Path:
    path = (ROOT / raw).resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise AuthorizationPreparationV2Error(f"path escapes repository: {raw}") from exc
    require(relative.startswith(prefix), f"path outside allowed root {prefix}: {raw}")
    require(path.is_file(), f"required file missing: {raw}")
    return path


def build_policy(role_logins: dict[str, list[str]], auth: ModuleType) -> dict[str, Any]:
    require(set(role_logins) == set(auth.ROLES), "role login map does not match canonical approval roles")
    return {
        "schema_version": 2,
        "kind": auth.POLICY_KIND,
        "repository": auth.EXPECTED_REPOSITORY,
        "pull_request": auth.EXPECTED_PR,
        "base_ref": auth.EXPECTED_BASE_REF,
        "head_ref": auth.EXPECTED_HEAD_REF,
        "minimum_distinct_actors": 3,
        "roles": {
            role: {"allowed_logins": list(role_logins[role])}
            for role in auth.ROLES
        },
        "separation_of_duties": [
            ["engineering", "security"],
            ["security", "release_owner"],
        ],
        "require_human_reviewers": True,
        "require_exact_evidence_head_review_commit": True,
        "require_pr_author_exclusion": True,
        "require_latest_decisive_review": True,
    }


def output_directory(release_id: str) -> Path:
    require(bool(SAFE_ID.fullmatch(release_id)) and release_id.upper() != "PENDING", "release_id must be a concrete safe identifier")
    path = (ROOT / "reports" / "final-acceptance" / release_id / "pre-final").resolve()
    allowed = (ROOT / "reports" / "final-acceptance").resolve()
    try:
        path.relative_to(allowed)
    except ValueError as exc:
        raise AuthorizationPreparationV2Error("authorization output escapes final-acceptance reports") from exc
    return path


def prepare(
    *,
    release_id: str,
    production_manifest_path: Path,
    role_logins: dict[str, list[str]],
    handoff: dict[str, str],
) -> dict[str, Any]:
    assembler = load_module(ASSEMBLER_V2, "lumi_authorization_prep_assembler_v2")
    auth = load_module(AUTHORIZATION_V2, "lumi_authorization_prep_validator_v2")
    feasibility = load_module(FEASIBILITY_V2, "lumi_authorization_prep_feasibility_v2")
    try:
        _production, source_rc = assembler.validate_production_manifest(production_manifest_path)
    except assembler.AssemblyV2Error as exc:
        raise AuthorizationPreparationV2Error(f"production manifest invalid: {exc}") from exc

    require(set(handoff) == set(HANDOFF_KEYS), "operational handoff key set mismatch")
    for key, value in handoff.items():
        require(isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING", f"operational handoff {key} is missing/PENDING")

    policy = build_policy(role_logins, auth)
    try:
        feasibility_result = feasibility.validate_policy(policy)
    except feasibility.ApprovalPolicyFeasibilityError as exc:
        raise AuthorizationPreparationV2Error(f"approval principal policy is not feasible: {exc}") from exc

    out = output_directory(release_id)
    policy_path = out / "approval-policy-v2.json"
    request_path = out / "authorization-request-v2.json"
    require(not policy_path.exists() and not request_path.exists(), "pre-final authorization files already exist; refuse overwrite")
    out.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    request = {
        "schema_version": 2,
        "kind": auth.REQUEST_KIND,
        "release_id": release_id,
        "source_release_candidate": {
            "git_sha": source_rc[0],
            "version": source_rc[1],
            "migration_head": source_rc[2],
        },
        "repository": auth.EXPECTED_REPOSITORY,
        "pull_request": auth.EXPECTED_PR,
        "approval_policy": auth.frozen(policy_path),
        "operational_handoff": {key: handoff[key].strip() for key in HANDOFF_KEYS},
    }
    try:
        normalized_request, normalized_policy_path, normalized_policy = auth.validate_request(request)
        feasibility.validate_policy(normalized_policy)
    except (auth.ReleaseAuthorizationV2Error, feasibility.ApprovalPolicyFeasibilityError) as exc:
        raise AuthorizationPreparationV2Error(f"generated authorization request failed canonical validation: {exc}") from exc
    require(normalized_policy_path.resolve() == policy_path.resolve(), "generated authorization request policy path drift")
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "schema_version": 2,
        "kind": "LUMI_RELEASE_AUTHORIZATION_PREPARATION_V2",
        "status": "PASS",
        "release_id": release_id,
        "source_release_candidate": normalized_request["source_release_candidate"],
        "approval_policy": auth.frozen(policy_path),
        "authorization_request": auth.frozen(request_path),
        "minimum_distinct_actors": feasibility_result["minimum_distinct_actors"],
        "distinct_candidate_count": feasibility_result["distinct_candidate_count"],
        "excluded_logins": feasibility_result["excluded_logins"],
        "feasible_assignment": feasibility_result["feasible_assignment"],
    }


def self_test() -> dict[str, Any]:
    release_id = "_node73-auth-prep-v2-selftest"
    release_root = ROOT / "reports" / "final-acceptance" / release_id
    production_root = ROOT / "reports" / "production-deployments" / release_id
    for path in (release_root, production_root):
        if path.exists():
            shutil.rmtree(path)
    production_root.mkdir(parents=True, exist_ok=True)
    production = production_root / "manifest.json"
    production.write_text(json.dumps({
        "schema_version": 1,
        "deployment_id": release_id,
        "environment": "production",
        "release_candidate": {
            "git_sha": "a" * 40,
            "version": "1.0.0-rc.1",
            "migration_head": "0020_generation_operation_identity",
        },
        "edge": {"domain": "contract.example.invalid"},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    roles = {
        "product": ["alice"],
        "engineering": ["bob"],
        "security": ["carol"],
        "operations": ["alice", "dave"],
        "release_owner": ["dave"],
    }
    handoff = {key: f"{key}-owner" for key in HANDOFF_KEYS}
    try:
        clean = prepare(
            release_id=release_id,
            production_manifest_path=production,
            role_logins=roles,
            handoff=handoff,
        )
        require(clean["status"] == "PASS" and clean["distinct_candidate_count"] >= 3, "clean authorization preparation did not PASS")
        blocked = 0
        impossible = dict(roles)
        impossible = {role: ["alice"] for role in impossible}
        other_release = release_id + "-bad"
        other_root = ROOT / "reports" / "final-acceptance" / other_release
        if other_root.exists():
            shutil.rmtree(other_root)
        try:
            prepare(
                release_id=other_release,
                production_manifest_path=production,
                role_logins=impossible,
                handoff=handoff,
            )
        except AuthorizationPreparationV2Error:
            blocked += 1
        else:
            raise AuthorizationPreparationV2Error("impossible approval policy did not block pre-final preparation")
        return {"status": "PASS", "clean": clean, "negative_drills": blocked}
    finally:
        for path in (release_root, production_root, ROOT / "reports" / "final-acceptance" / (release_id + "-bad")):
            if path.exists():
                shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare canonical NODE-73 V2 approval policy and authorization request")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--production-manifest", required=True)
    for _role, option in ROLE_INPUTS.items():
        parser.add_argument(f"--{option.replace('_', '-')}", required=True)
    for key in HANDOFF_KEYS:
        parser.add_argument(f"--{key.replace('_', '-')}", required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            print(json.dumps(self_test(), indent=2, sort_keys=True))
            return 0
        production = repo_file(args.production_manifest, prefix="reports/production-deployments/")
        roles = {
            role: parse_logins(getattr(args, option), label=option)
            for role, option in ROLE_INPUTS.items()
        }
        handoff = {key: getattr(args, key) for key in HANDOFF_KEYS}
        result = prepare(
            release_id=args.release_id,
            production_manifest_path=production,
            role_logins=roles,
            handoff=handoff,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (AuthorizationPreparationV2Error, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release authorization preparation V2 blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
