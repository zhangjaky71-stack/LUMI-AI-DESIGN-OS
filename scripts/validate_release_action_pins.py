#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
PINS_PATH = ROOT / "production" / "release-actions" / "pins-v1.json"
DISPATCH_REGISTRY_CONTRACT = ROOT / "scripts" / "validate_release_dispatch_registry_contract.py"
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
USES_LINE = re.compile(r"^\s*-\s+uses:\s+([^\s#]+)(?:\s+#\s*(\S+))?\s*$")
PRODUCTION_ENVIRONMENT = re.compile(r"(?m)^\s*environment:\s*production\s*$")
STAGING_ENVIRONMENT = re.compile(r"(?m)^\s*environment:\s*staging\s*$")
ID_TOKEN_WRITE = re.compile(r"(?m)^\s*id-token:\s*write\s*$")
CONTENTS_WRITE = re.compile(r"(?m)^\s*contents:\s*write\s*$")
CANONICAL_GATE_NAME = re.compile(
    r"(?mi)^name:\s*.*(?:Release Gate|Acceptance Gate)\s*$"
)
RELEASE_EVIDENCE_ROOTS = (
    "reports/staging-acceptance",
    "reports/production-deployments",
    "reports/production-recovery",
    "reports/security-release",
    "reports/final-acceptance",
)


class ReleaseActionPinError(RuntimeError):
    pass


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReleaseActionPinError(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow_list(policy: dict[str, Any], key: str, *, required: bool) -> list[str]:
    value = policy.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, list) or (required and not value):
        raise ReleaseActionPinError(f"{key} must be a non-empty list")
    if len(value) != len(set(value)):
        raise ReleaseActionPinError(f"{key} contains duplicates")
    normalized: list[str] = []
    for relative in value:
        if not isinstance(relative, str) or not relative.startswith(".github/workflows/"):
            raise ReleaseActionPinError(f"invalid workflow path in {key}: {relative!r}")
        normalized.append(relative)
    return normalized


def _load_policy() -> dict[str, Any]:
    try:
        policy = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseActionPinError(f"unable to read release action pin policy: {exc}") from exc
    if not isinstance(policy, dict):
        raise ReleaseActionPinError("release action pin policy must be a JSON object")
    if policy.get("schema_version") != 1 or policy.get("policy") != "LUMI_RELEASE_ACTION_PINS_V1":
        raise ReleaseActionPinError("release action pin policy schema/kind mismatch")
    actions = policy.get("actions")
    critical = _workflow_list(policy, "release_critical_workflows", required=True)
    evidence = _workflow_list(policy, "release_evidence_workflows", required=False)
    if set(critical) & set(evidence):
        raise ReleaseActionPinError("release critical/evidence workflow lists must be disjoint")
    if not isinstance(actions, dict) or not actions:
        raise ReleaseActionPinError("release action pin policy actions map is missing")
    for action, releases in actions.items():
        if not isinstance(action, str) or action.count("/") != 1:
            raise ReleaseActionPinError(f"invalid action repository key: {action!r}")
        if not isinstance(releases, list) or not releases:
            raise ReleaseActionPinError(f"action {action} has no approved immutable releases")
        seen_shas: set[str] = set()
        for release in releases:
            if not isinstance(release, dict):
                raise ReleaseActionPinError(f"action {action} release entry must be an object")
            version = release.get("version")
            sha = release.get("sha")
            if not isinstance(version, str) or not version.startswith("v"):
                raise ReleaseActionPinError(f"action {action} release version is invalid")
            if not isinstance(sha, str) or not SHA40.fullmatch(sha):
                raise ReleaseActionPinError(f"action {action}@{version} must use a full lowercase SHA40")
            if sha in seen_shas:
                raise ReleaseActionPinError(f"action {action} repeats approved SHA {sha}")
            seen_shas.add(sha)
    policy["release_critical_workflows"] = critical
    policy["release_evidence_workflows"] = evidence
    return policy


def _approved(policy: dict[str, Any], action: str, sha: str, version: str | None) -> bool:
    actions = policy["actions"]
    releases = actions.get(action)
    if not isinstance(releases, list):
        return False
    for release in releases:
        if release.get("sha") == sha and release.get("version") == version:
            return True
    return False


def _action_repository(action_path: str) -> str:
    parts = action_path.split("/")
    if len(parts) < 2 or any(not part for part in parts[:2]):
        raise ReleaseActionPinError(f"unsupported external action repository path: {action_path!r}")
    return "/".join(parts[:2])


def _validate_uses_target(
    *,
    policy: dict[str, Any],
    workflow: str,
    line_no: int,
    target: str,
    version_comment: str | None,
) -> tuple[str, str, str] | None:
    if target.startswith("./"):
        return None
    if "@" not in target:
        raise ReleaseActionPinError(f"{workflow}:{line_no}: external action is missing @ref: {target}")
    action_path, ref = target.rsplit("@", 1)
    try:
        action = _action_repository(action_path)
    except ReleaseActionPinError as exc:
        raise ReleaseActionPinError(f"{workflow}:{line_no}: {exc}") from exc
    if not SHA40.fullmatch(ref):
        raise ReleaseActionPinError(
            f"{workflow}:{line_no}: {action_path} must be pinned to a full lowercase 40-character commit SHA"
        )
    if version_comment is None:
        raise ReleaseActionPinError(
            f"{workflow}:{line_no}: {action_path}@{ref} must carry its approved version comment"
        )
    if not _approved(policy, action, ref, version_comment):
        raise ReleaseActionPinError(
            f"{workflow}:{line_no}: unapproved release action pin {action_path}@{ref} # {version_comment}"
        )
    return action, ref, version_comment


def validate_workflow_text(*, policy: dict[str, Any], workflow: str, text: str) -> int:
    external = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "uses:" not in line:
            continue
        match = USES_LINE.fullmatch(line)
        if match is None:
            raise ReleaseActionPinError(f"{workflow}:{line_no}: malformed or unauditable uses line")
        result = _validate_uses_target(
            policy=policy,
            workflow=workflow,
            line_no=line_no,
            target=match.group(1),
            version_comment=match.group(2),
        )
        if result is not None:
            external += 1
    if external == 0:
        raise ReleaseActionPinError(f"{workflow}: governed workflow has no external action steps")
    return external


def _sensitive_workflow_reasons(text: str) -> tuple[str, ...]:
    reasons: list[str] = []
    if PRODUCTION_ENVIRONMENT.search(text):
        reasons.append("production-environment")
    if (
        STAGING_ENVIRONMENT.search(text)
        and ID_TOKEN_WRITE.search(text)
        and "reports/staging-acceptance" in text
    ):
        reasons.append("staging-oidc-release-evidence")
    if (
        CONTENTS_WRITE.search(text)
        and "git push origin" in text
        and any(root in text for root in RELEASE_EVIDENCE_ROOTS)
    ):
        reasons.append("release-evidence-git-push")
    if CANONICAL_GATE_NAME.search(text):
        reasons.append("canonical-release-gate")
    return tuple(reasons)


def _repository_workflow_texts() -> dict[str, str]:
    if not WORKFLOW_ROOT.is_dir():
        raise ReleaseActionPinError("workflow directory is missing")
    workflows: dict[str, str] = {}
    for path in sorted([*WORKFLOW_ROOT.glob("*.yml"), *WORKFLOW_ROOT.glob("*.yaml")]):
        workflows[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
    if not workflows:
        raise ReleaseActionPinError("repository has no GitHub workflows to audit")
    return workflows


def _validate_sensitive_workflow_coverage(
    policy: dict[str, Any],
    *,
    workflow_texts: Mapping[str, str] | None = None,
) -> dict[str, tuple[str, ...]]:
    texts = dict(workflow_texts) if workflow_texts is not None else _repository_workflow_texts()
    governed = set(policy["release_critical_workflows"]) | set(policy["release_evidence_workflows"])
    discovered = {
        workflow: reasons
        for workflow, text in texts.items()
        if (reasons := _sensitive_workflow_reasons(text))
    }
    missing = sorted(set(discovered) - governed)
    if missing:
        details = "; ".join(
            f"{workflow}={','.join(discovered[workflow])}" for workflow in missing
        )
        raise ReleaseActionPinError(
            "sensitive release workflow is outside immutable action-pin governance: " + details
        )
    return dict(sorted(discovered.items()))


def _negative_drills(policy: dict[str, Any]) -> None:
    good = "    - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6.1.0\n"
    if validate_workflow_text(policy=policy, workflow="fixture.yml", text=good) != 1:
        raise ReleaseActionPinError("clean full-SHA fixture did not pass")
    subaction = "    - uses: github/codeql-action/analyze@ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd # v4.37.7\n"
    if validate_workflow_text(policy=policy, workflow="subaction-fixture.yml", text=subaction) != 1:
        raise ReleaseActionPinError("clean pinned sub-action fixture did not pass")

    blocked = (
        "    - uses: actions/checkout@v6\n",
        "    - uses: actions/checkout@d23441a # v6.1.0\n",
        "    - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803\n",
        "    - uses: actions/checkout@0000000000000000000000000000000000000000 # v6.1.0\n",
        "    - uses: attacker/example@d23441a48e516b6c34aea4fa41551a30e30af803 # v6.1.0\n",
        "    - uses: github/codeql-action/analyze@0000000000000000000000000000000000000000 # v4.37.7\n",
    )
    for index, text in enumerate(blocked, start=1):
        try:
            validate_workflow_text(policy=policy, workflow=f"negative-{index}.yml", text=text)
        except ReleaseActionPinError:
            continue
        raise ReleaseActionPinError(f"negative release-action pin drill {index} did not block")

    sensitive_fixtures = {
        ".github/workflows/unguarded-production.yml": """
name: Unguarded Production
jobs:
  write:
    environment: production
    runs-on: ubuntu-latest
""",
        ".github/workflows/unguarded-staging-evidence.yml": """
name: Unguarded Staging Evidence
permissions:
  id-token: write
jobs:
  collect:
    environment: staging
    runs-on: ubuntu-latest
    steps:
      - run: mkdir -p reports/staging-acceptance/runtime
""",
        ".github/workflows/unguarded-freeze.yml": """
name: Unguarded Freeze
permissions:
  contents: write
jobs:
  freeze:
    runs-on: ubuntu-latest
    steps:
      - run: |
          mkdir -p reports/security-release/example
          git push origin HEAD:release
""",
        ".github/workflows/unguarded-release-gate.yml": """
name: Example Release Gate
jobs:
  gate:
    runs-on: ubuntu-latest
""",
    }
    for index, (workflow, text) in enumerate(sensitive_fixtures.items(), start=1):
        try:
            _validate_sensitive_workflow_coverage(
                policy,
                workflow_texts={workflow: text},
            )
        except ReleaseActionPinError:
            continue
        raise ReleaseActionPinError(f"sensitive workflow discovery drill {index} did not block")


def _validate_dispatch_registry() -> None:
    module = _load_module(DISPATCH_REGISTRY_CONTRACT, "lumi_release_dispatch_registry_contract")
    try:
        result = module.normalize_registry(module.load_json(module.REGISTRY), module.load_json(module.PINS))
        module.validate_local_release_workflows(result)
        self_result = module.self_test()
    except module.DispatchRegistryContractError as exc:
        raise ReleaseActionPinError(f"default-branch dispatch registry contract failed: {exc}") from exc
    if self_result.get("status") != "PASS" or self_result.get("negative_drills") != 5:
        raise ReleaseActionPinError("default-branch dispatch registry self-test drift")
    if result.get("workflow_count") != 12:
        raise ReleaseActionPinError("default-branch dispatch registry must cover exactly twelve release-critical workflows")


def _validate_workflow_set(policy: dict[str, Any], workflows: list[str]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for relative in workflows:
        path = ROOT / relative
        if not path.is_file():
            raise ReleaseActionPinError(f"governed workflow is missing: {relative}")
        totals[relative] = validate_workflow_text(
            policy=policy,
            workflow=relative,
            text=path.read_text(encoding="utf-8"),
        )
    return totals


def main() -> int:
    policy = _load_policy()
    critical = _validate_workflow_set(policy, policy["release_critical_workflows"])
    evidence = _validate_workflow_set(policy, policy["release_evidence_workflows"])
    discovered_sensitive = _validate_sensitive_workflow_coverage(policy)
    _negative_drills(policy)
    _validate_dispatch_registry()
    print(
        json.dumps(
            {
                "status": "PASS",
                "policy": policy["policy"],
                "release_critical_workflow_count": len(critical),
                "release_evidence_workflow_count": len(evidence),
                "external_action_steps": sum(critical.values()) + sum(evidence.values()),
                "dispatch_registry_bound": True,
                "sensitive_workflow_discovery_bound": True,
                "sensitive_workflows": discovered_sensitive,
                "release_critical_workflows": critical,
                "release_evidence_workflows": evidence,
                "negative_drills": {
                    "floating_tag_blocked": True,
                    "short_sha_blocked": True,
                    "missing_version_annotation_blocked": True,
                    "unknown_sha_blocked": True,
                    "unknown_action_blocked": True,
                    "subaction_unknown_sha_blocked": True,
                    "unguarded_production_workflow_blocked": True,
                    "unguarded_staging_evidence_blocked": True,
                    "unguarded_evidence_push_blocked": True,
                    "unguarded_release_gate_blocked": True
                }
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseActionPinError as exc:
        raise SystemExit(f"release action pin contract failed: {exc}") from exc
