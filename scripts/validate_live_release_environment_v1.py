#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "final" / "acceptance" / "release-environment-policy-template.json"
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
EXPECTED_ENVIRONMENT = "production"
POLICY_KIND = "LUMI_RELEASE_ENVIRONMENT_POLICY_V1"
REPORT_KIND = "LUMI_LIVE_RELEASE_ENVIRONMENT_V1"


class ReleaseEnvironmentError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseEnvironmentError(message)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def validate_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    require(payload.get("schema_version") == 1, "release environment policy schema_version must be 1")
    require(payload.get("kind") == POLICY_KIND, "release environment policy kind mismatch")
    require(payload.get("repository") == EXPECTED_REPOSITORY, "release environment policy repository mismatch")
    require(payload.get("environment") == EXPECTED_ENVIRONMENT, "release environment policy environment mismatch")
    minimum = payload.get("minimum_required_reviewers")
    require(isinstance(minimum, int) and not isinstance(minimum, bool) and minimum >= 1, "minimum_required_reviewers must be >= 1")
    require(payload.get("require_prevent_self_review") is True, "production environment must require prevent_self_review")
    branch_policy = payload.get("deployment_branch_policy")
    require(isinstance(branch_policy, Mapping), "deployment_branch_policy is missing")
    require(branch_policy.get("protected_branches") is True, "production environment must require protected branches")
    require(branch_policy.get("custom_branch_policies") is False, "production environment must not use custom branch policies")
    return {
        "schema_version": 1,
        "kind": POLICY_KIND,
        "repository": EXPECTED_REPOSITORY,
        "environment": EXPECTED_ENVIRONMENT,
        "minimum_required_reviewers": minimum,
        "require_prevent_self_review": True,
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
    }


def reviewer_identity(item: Mapping[str, Any]) -> str:
    reviewer_type = item.get("type")
    reviewer = item.get("reviewer")
    require(reviewer_type in {"User", "Team"}, "production environment reviewer type must be User or Team")
    require(isinstance(reviewer, Mapping), "production environment reviewer metadata missing")
    if reviewer_type == "User":
        login = reviewer.get("login")
        require(isinstance(login, str) and bool(login), "production environment user reviewer login missing")
        return f"user:{login}"
    slug = reviewer.get("slug")
    require(isinstance(slug, str) and bool(slug), "production environment team reviewer slug missing")
    return f"team:{slug}"


def validate_environment(payload: Mapping[str, Any], policy_payload: Mapping[str, Any]) -> dict[str, Any]:
    policy = validate_policy(policy_payload)
    require(payload.get("name") == EXPECTED_ENVIRONMENT, "GitHub environment name mismatch")
    rules = payload.get("protection_rules")
    require(isinstance(rules, list), "GitHub production protection_rules missing")
    reviewer_rules = [rule for rule in rules if isinstance(rule, Mapping) and rule.get("type") == "required_reviewers"]
    require(len(reviewer_rules) == 1, "production environment must contain exactly one required_reviewers protection rule")
    reviewer_rule = reviewer_rules[0]
    require(reviewer_rule.get("prevent_self_review") is True, "production environment must prevent self-review")
    reviewers_raw = reviewer_rule.get("reviewers")
    require(isinstance(reviewers_raw, list), "production environment required reviewers list missing")
    reviewers = sorted({reviewer_identity(item) for item in reviewers_raw if isinstance(item, Mapping)})
    require(len(reviewers) >= int(policy["minimum_required_reviewers"]), "production environment has too few required reviewers")

    branch_policy = payload.get("deployment_branch_policy")
    require(isinstance(branch_policy, Mapping), "GitHub production deployment_branch_policy missing")
    require(branch_policy.get("protected_branches") is True, "production environment does not restrict deployment to protected branches")
    require(branch_policy.get("custom_branch_policies") is False, "production environment custom branch policy mode is not allowed")

    return {
        "status": "PASS",
        "environment": EXPECTED_ENVIRONMENT,
        "required_reviewer_count": len(reviewers),
        "required_reviewers": reviewers,
        "prevent_self_review": True,
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
        "environment_policy_bound": True,
    }


def fetch_environment(repository: str, *, token: str | None) -> dict[str, Any]:
    require(repository == EXPECTED_REPOSITORY, "release environment repository mismatch")
    encoded = urllib.parse.quote(EXPECTED_ENVIRONMENT, safe="")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "lumi-node73-release-environment-v1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/environments/{encoded}",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ReleaseEnvironmentError(
            f"GitHub production environment lookup failed with HTTP {exc.code}; Actions read permission may be required"
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ReleaseEnvironmentError(f"GitHub production environment lookup failed: {exc}") from exc
    require(isinstance(payload, dict), "GitHub production environment lookup returned non-object JSON")
    return payload


def capture(repository: str, *, token: str | None) -> dict[str, Any]:
    policy = load_json(POLICY_PATH)
    payload = fetch_environment(repository, token=token)
    result = validate_environment(payload, policy)
    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repository": EXPECTED_REPOSITORY,
        **result,
    }


def self_test() -> dict[str, Any]:
    policy = load_json(POLICY_PATH)
    good = {
        "name": EXPECTED_ENVIRONMENT,
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": True,
                "reviewers": [
                    {"type": "User", "reviewer": {"login": "alice"}},
                    {"type": "Team", "reviewer": {"slug": "release-managers"}},
                ],
            }
        ],
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
    }
    clean = validate_environment(good, policy)
    mutations = [
        {**good, "name": "staging"},
        {**good, "protection_rules": []},
        {**good, "protection_rules": [{**good["protection_rules"][0], "prevent_self_review": False}]},
        {**good, "protection_rules": [{**good["protection_rules"][0], "reviewers": []}]},
        {**good, "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}},
    ]
    blocked = 0
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate_environment(mutation, policy)
        except ReleaseEnvironmentError:
            blocked += 1
            continue
        raise ReleaseEnvironmentError(f"negative release environment drill did not block: {index}")
    return {"status": "PASS", "clean": clean, "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live NODE-73 production environment governance")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", EXPECTED_REPOSITORY))
    parser.add_argument("--token-env", default="RELEASE_APPROVAL_TOKEN")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        result = self_test() if args.self_test else capture(args.repository, token=os.environ.get(args.token_env))
    except (ReleaseEnvironmentError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release environment governance blocked: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
