#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PINS_PATH = ROOT / "production" / "release-actions" / "pins-v1.json"
DISPATCH_REGISTRY_CONTRACT = ROOT / "scripts" / "validate_release_dispatch_registry_contract.py"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
USES_LINE = re.compile(r"^\s*-\s+uses:\s+([^\s#]+)(?:\s+#\s*(\S+))?\s*$")


class ReleaseActionPinError(RuntimeError):
    pass


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReleaseActionPinError(f"unable to import {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    workflows = policy.get("release_critical_workflows")
    if not isinstance(actions, dict) or not actions:
        raise ReleaseActionPinError("release action pin policy actions map is missing")
    if not isinstance(workflows, list) or not workflows:
        raise ReleaseActionPinError("release-critical workflow list is missing")
    if len(workflows) != len(set(workflows)):
        raise ReleaseActionPinError("release-critical workflow list contains duplicates")
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
    action, ref = target.rsplit("@", 1)
    if action.count("/") != 1:
        raise ReleaseActionPinError(f"{workflow}:{line_no}: unsupported external action target: {target}")
    if not SHA40.fullmatch(ref):
        raise ReleaseActionPinError(
            f"{workflow}:{line_no}: {action} must be pinned to a full lowercase 40-character commit SHA"
        )
    if version_comment is None:
        raise ReleaseActionPinError(
            f"{workflow}:{line_no}: {action}@{ref} must carry its approved version comment"
        )
    if not _approved(policy, action, ref, version_comment):
        raise ReleaseActionPinError(
            f"{workflow}:{line_no}: unapproved release action pin {action}@{ref} # {version_comment}"
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
        raise ReleaseActionPinError(f"{workflow}: release-critical workflow has no external action steps")
    return external


def _negative_drills(policy: dict[str, Any]) -> None:
    good = "    - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6.1.0\n"
    if validate_workflow_text(policy=policy, workflow="fixture.yml", text=good) != 1:
        raise ReleaseActionPinError("clean full-SHA fixture did not pass")

    blocked = (
        "    - uses: actions/checkout@v6\n",
        "    - uses: actions/checkout@d23441a # v6.1.0\n",
        "    - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803\n",
        "    - uses: actions/checkout@0000000000000000000000000000000000000000 # v6.1.0\n",
        "    - uses: attacker/example@d23441a48e516b6c34aea4fa41551a30e30af803 # v6.1.0\n",
    )
    for index, text in enumerate(blocked, start=1):
        try:
            validate_workflow_text(policy=policy, workflow=f"negative-{index}.yml", text=text)
        except ReleaseActionPinError:
            continue
        raise ReleaseActionPinError(f"negative release-action pin drill {index} did not block")


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
    if result.get("workflow_count") != 9:
        raise ReleaseActionPinError("default-branch dispatch registry must cover exactly nine release-critical workflows")


def main() -> int:
    policy = _load_policy()
    workflows = policy["release_critical_workflows"]
    totals: dict[str, int] = {}
    for relative in workflows:
        if not isinstance(relative, str) or not relative.startswith(".github/workflows/"):
            raise ReleaseActionPinError(f"invalid release-critical workflow path: {relative!r}")
        path = ROOT / relative
        if not path.is_file():
            raise ReleaseActionPinError(f"release-critical workflow is missing: {relative}")
        totals[relative] = validate_workflow_text(
            policy=policy,
            workflow=relative,
            text=path.read_text(encoding="utf-8"),
        )
    _negative_drills(policy)
    _validate_dispatch_registry()
    print(
        json.dumps(
            {
                "status": "PASS",
                "policy": policy["policy"],
                "workflow_count": len(totals),
                "external_action_steps": sum(totals.values()),
                "dispatch_registry_bound": True,
                "workflows": totals,
                "negative_drills": {
                    "floating_tag_blocked": True,
                    "short_sha_blocked": True,
                    "missing_version_annotation_blocked": True,
                    "unknown_sha_blocked": True,
                    "unknown_action_blocked": True
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
