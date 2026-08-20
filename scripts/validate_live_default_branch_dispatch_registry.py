#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "production" / "release-actions" / "default-branch-dispatch-registry-v1.json"
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
EXPECTED_DEFAULT_BRANCH = "main"
EXPECTED_RELEASE_REF = "release-closure-p0"
EXPECTED_MODE = "FAIL_CLOSED_REGISTRY_STUB"
REPORT_KIND = "LUMI_LIVE_DEFAULT_BRANCH_DISPATCH_REGISTRY_V1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class LiveDispatchRegistryError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveDispatchRegistryError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveDispatchRegistryError(f"unable to read JSON {path}: {exc}") from exc
    require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def workflow_dispatch_inputs_block(text: str) -> str:
    lines = text.splitlines()
    dispatch_index = -1
    for index, line in enumerate(lines):
        if indent(line) == 2 and line.strip() == "workflow_dispatch:":
            require(dispatch_index < 0, "workflow contains more than one top-level workflow_dispatch block")
            dispatch_index = index
    require(dispatch_index >= 0, "workflow_dispatch block is missing")

    dispatch_end = len(lines)
    for index in range(dispatch_index + 1, len(lines)):
        line = lines[index]
        if line.strip() and indent(line) <= 2:
            dispatch_end = index
            break

    inputs_index = -1
    for index in range(dispatch_index + 1, dispatch_end):
        line = lines[index]
        if indent(line) == 4 and line.strip() == "inputs:":
            inputs_index = index
            break
    if inputs_index < 0:
        return ""

    inputs_end = dispatch_end
    for index in range(inputs_index + 1, dispatch_end):
        line = lines[index]
        if line.strip() and indent(line) <= 4:
            inputs_end = index
            break
    return "\n".join(line.rstrip() for line in lines[inputs_index:inputs_end]).rstrip()


def workflow_dispatch_input_names(block: str) -> list[str]:
    if not block:
        return []
    names: list[str] = []
    for line in block.splitlines()[1:]:
        if indent(line) == 6:
            stripped = line.strip()
            if stripped.endswith(":"):
                name = stripped[:-1]
                require(bool(name), "workflow_dispatch input has empty name")
                names.append(name)
    require(len(names) == len(set(names)), "workflow_dispatch inputs contain duplicate names")
    return names


def validate_default_stub(*, path: str, stub_text: str, release_text: str) -> dict[str, Any]:
    expected_inputs = workflow_dispatch_inputs_block(release_text)
    observed_inputs = workflow_dispatch_inputs_block(stub_text)
    require(
        observed_inputs == expected_inputs,
        f"default-branch workflow_dispatch input schema drift for {path}",
    )
    require("permissions:\n  contents: read\n" in stub_text, f"default-branch registry stub must be contents:read: {path}")
    for forbidden in (
        "contents: write",
        "actions: write",
        "packages: write",
        "attestations: write",
        "id-token: write",
        "pull-requests: write",
        "environment:",
        "${{ secrets.",
        "uses:",
    ):
        require(forbidden not in stub_text, f"default-branch registry stub contains forbidden capability {forbidden!r}: {path}")
    for forbidden_event in ("pull_request:", "push:", "schedule:", "workflow_run:"):
        require(forbidden_event not in stub_text, f"default-branch registry stub contains non-dispatch event {forbidden_event}: {path}")
    require("jobs:\n  default-branch-registry-only:\n" in stub_text, f"default-branch registry-only job missing: {path}")
    require("Refuse default-branch execution" in stub_text, f"default-branch refusal step missing: {path}")
    require("ref=release-closure-p0" in stub_text, f"default-branch stub does not direct execution to release ref: {path}")
    require(re.search(r"(?m)^\s*exit 64\s*$", stub_text) is not None, f"default-branch registry stub must fail closed with exit 64: {path}")
    return {
        "dispatch_inputs": workflow_dispatch_input_names(observed_inputs),
        "input_schema_sha256": sha256_bytes(observed_inputs.encode("utf-8")),
    }


def _api_json(url: str, *, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "lumi-node73-finalization-v2",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LiveDispatchRegistryError(f"GitHub API read failed for {url}: {exc}") from exc
    require(isinstance(payload, dict), f"GitHub API response must be an object: {url}")
    return payload


def _branch_head(repository: str, branch: str, *, token: str) -> str:
    encoded = urllib.parse.quote(branch, safe="")
    payload = _api_json(f"https://api.github.com/repos/{repository}/branches/{encoded}", token=token)
    commit = payload.get("commit")
    require(isinstance(commit, Mapping), f"GitHub branch metadata missing commit for {branch}")
    sha = commit.get("sha")
    require(isinstance(sha, str) and bool(SHA40.fullmatch(sha.lower())), f"GitHub branch head is not SHA40 for {branch}")
    return sha.lower()


def _contents(repository: str, path: str, ref: str, *, token: str) -> tuple[str, str]:
    encoded_path = urllib.parse.quote(path, safe="/")
    encoded_ref = urllib.parse.quote(ref, safe="")
    payload = _api_json(
        f"https://api.github.com/repos/{repository}/contents/{encoded_path}?ref={encoded_ref}",
        token=token,
    )
    require(payload.get("type") == "file", f"default-branch registry path is not a file: {path}")
    blob_sha = payload.get("sha")
    content = payload.get("content")
    encoding = payload.get("encoding")
    require(isinstance(blob_sha, str) and len(blob_sha) == 40, f"GitHub blob SHA missing for {path}")
    require(isinstance(content, str) and encoding == "base64", f"GitHub file content is not base64 for {path}")
    try:
        raw = base64.b64decode(content, validate=False)
        text = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise LiveDispatchRegistryError(f"unable to decode GitHub file content for {path}: {exc}") from exc
    return blob_sha.lower(), text


def validate_registry_policy(payload: Mapping[str, Any]) -> list[str]:
    require(payload.get("schema_version") == 1, "dispatch registry policy schema_version must be 1")
    require(payload.get("policy") == "LUMI_RELEASE_DEFAULT_BRANCH_DISPATCH_REGISTRY_V1", "dispatch registry policy kind mismatch")
    require(payload.get("repository") == EXPECTED_REPOSITORY, "dispatch registry repository mismatch")
    require(payload.get("default_branch") == EXPECTED_DEFAULT_BRANCH, "dispatch registry default branch mismatch")
    require(payload.get("release_ref") == EXPECTED_RELEASE_REF, "dispatch registry release ref mismatch")
    require(
        payload.get("registry_behavior") == "DEFAULT_BRANCH_DISCOVERY_ONLY_RELEASE_REF_EXECUTION",
        "dispatch registry behavior mismatch",
    )
    workflows = payload.get("workflows")
    require(isinstance(workflows, list) and workflows, "dispatch registry workflows missing")
    paths: list[str] = []
    for item in workflows:
        require(isinstance(item, Mapping), "dispatch registry workflow entry must be an object")
        path = item.get("path")
        require(isinstance(path, str) and path.startswith(".github/workflows/"), "invalid dispatch registry path")
        require(item.get("default_branch_mode") == EXPECTED_MODE, f"default branch mode must be fail-closed stub: {path}")
        paths.append(path)
    require(len(paths) == len(set(paths)), "dispatch registry contains duplicate paths")
    return sorted(paths)


def capture(repository: str, *, token: str) -> dict[str, Any]:
    require(repository == EXPECTED_REPOSITORY, "live dispatch registry repository mismatch")
    require(bool(token.strip()), "GitHub read token is missing")
    registry = load_json(REGISTRY_PATH)
    paths = validate_registry_policy(registry)
    main_head = _branch_head(repository, EXPECTED_DEFAULT_BRANCH, token=token)

    workflows: list[dict[str, Any]] = []
    for path in paths:
        release_path = ROOT / path
        require(release_path.is_file(), f"release-ref workflow missing from Evidence Head checkout: {path}")
        release_text = release_path.read_text(encoding="utf-8")
        require("workflow_dispatch:" in release_text, f"release-ref workflow lost workflow_dispatch: {path}")
        blob_sha, stub_text = _contents(repository, path, EXPECTED_DEFAULT_BRANCH, token=token)
        validation = validate_default_stub(path=path, stub_text=stub_text, release_text=release_text)
        workflows.append(
            {
                "path": path,
                "default_branch_blob_sha": blob_sha,
                "default_branch_sha256": sha256_bytes(stub_text.encode("utf-8")),
                **validation,
            }
        )

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "status": "PASS",
        "repository": EXPECTED_REPOSITORY,
        "default_branch": EXPECTED_DEFAULT_BRANCH,
        "default_branch_head_sha": main_head,
        "release_ref": EXPECTED_RELEASE_REF,
        "registry_policy_sha256": sha256_bytes(REGISTRY_PATH.read_bytes()),
        "workflow_count": len(workflows),
        "workflows": workflows,
        "all_default_branch_workflows_fail_closed": True,
        "dispatch_input_schemas_bound_to_evidence_head": True,
    }


def self_test() -> dict[str, Any]:
    release = """name: X\non:\n  workflow_dispatch:\n    inputs:\n      foo:\n        required: true\n        type: string\npermissions:\n  contents: read\njobs:\n  real:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo real\n"""
    clean = """name: X\non:\n  workflow_dispatch:\n    inputs:\n      foo:\n        required: true\n        type: string\npermissions:\n  contents: read\njobs:\n  default-branch-registry-only:\n    runs-on: ubuntu-24.04\n    steps:\n      - name: Refuse default-branch execution\n        run: |\n          echo ref=release-closure-p0\n          exit 64\n"""
    result = validate_default_stub(path=".github/workflows/x.yml", stub_text=clean, release_text=release)
    require(result.get("dispatch_inputs") == ["foo"], "clean default-branch stub fixture did not PASS")

    mutations = [
        clean.replace("foo:\n", "bar:\n", 1),
        clean.replace("contents: read", "contents: write"),
        clean.replace("steps:\n", "steps:\n      - uses: actions/checkout@deadbeef\n"),
        clean.replace("echo ref=release-closure-p0", "echo ${{ secrets.ADMIN }}"),
        clean.replace("exit 64", "exit 0"),
        clean.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n  pull_request:\n"),
    ]
    blocked = 0
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate_default_stub(path=f"negative-{index}.yml", stub_text=mutation, release_text=release)
        except LiveDispatchRegistryError:
            blocked += 1
            continue
        raise LiveDispatchRegistryError(f"negative live dispatch registry drill did not block: {index}")
    return {"status": "PASS", "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live default-branch workflow_dispatch registry for NODE-73")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repository", default=EXPECTED_REPOSITORY)
    parser.add_argument("--token-env", default="RELEASE_APPROVAL_TOKEN")
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        test_result = self_test()
        require(test_result.get("status") == "PASS" and test_result.get("negative_drills") == 6, "live dispatch registry self-test drift")
        if args.self_test:
            print(json.dumps(test_result, indent=2, sort_keys=True))
            return 0
        token = os.environ.get(args.token_env, "")
        report = capture(args.repository, token=token)
        if args.output:
            output = (ROOT / args.output).resolve()
            allowed = (ROOT / "reports" / "final-acceptance").resolve()
            try:
                output.relative_to(allowed)
            except ValueError as exc:
                raise LiveDispatchRegistryError("live dispatch registry output must stay below reports/final-acceptance/") from exc
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (LiveDispatchRegistryError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"live default-branch dispatch registry blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
