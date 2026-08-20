#!/usr/bin/env python3
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "production" / "release-actions" / "default-branch-dispatch-registry-v1.json"
PINS = ROOT / "production" / "release-actions" / "pins-v1.json"
EXPECTED_POLICY = "LUMI_RELEASE_DEFAULT_BRANCH_DISPATCH_REGISTRY_V1"
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
EXPECTED_DEFAULT_BRANCH = "main"
EXPECTED_RELEASE_REF = "release-closure-p0"
STUB_MODE = "FAIL_CLOSED_REGISTRY_STUB"
LOCK_PATH = ".github/workflows/regenerate-uv-lock.yml"


class DispatchRegistryContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DispatchRegistryContractError(message)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), f"{path.relative_to(ROOT)} must contain a JSON object")
    return payload


def normalize_registry(payload: Mapping[str, Any], pins: Mapping[str, Any]) -> dict[str, Any]:
    require(payload.get("schema_version") == 1, "dispatch registry schema_version must be 1")
    require(payload.get("policy") == EXPECTED_POLICY, "dispatch registry policy mismatch")
    require(payload.get("repository") == EXPECTED_REPOSITORY, "dispatch registry repository mismatch")
    require(payload.get("default_branch") == EXPECTED_DEFAULT_BRANCH, "dispatch registry default_branch mismatch")
    require(payload.get("release_ref") == EXPECTED_RELEASE_REF, "dispatch registry release_ref mismatch")
    require(
        payload.get("registry_behavior") == "DEFAULT_BRANCH_DISCOVERY_ONLY_RELEASE_REF_EXECUTION",
        "dispatch registry behavior mismatch",
    )

    release_critical = pins.get("release_critical_workflows")
    require(isinstance(release_critical, list) and release_critical, "release action pins missing release_critical_workflows")
    require(all(isinstance(path, str) for path in release_critical), "release_critical_workflows must contain strings")
    require(len(release_critical) == len(set(release_critical)), "release_critical_workflows contains duplicates")

    workflows = payload.get("workflows")
    require(isinstance(workflows, list) and workflows, "dispatch registry workflows must be a non-empty array")
    normalized: dict[str, str] = {}
    for item in workflows:
        require(isinstance(item, Mapping), "dispatch registry workflow entry must be an object")
        path = item.get("path")
        mode = item.get("default_branch_mode")
        require(
            isinstance(path, str)
            and path.startswith(".github/workflows/")
            and path.endswith((".yml", ".yaml")),
            "invalid dispatch registry workflow path",
        )
        require(path not in normalized, f"duplicate dispatch registry workflow path: {path}")
        require(mode == STUB_MODE, f"all default-branch release registry entries must be fail-closed stubs: {path}")
        normalized[path] = STUB_MODE

    require(
        set(normalized) == set(release_critical),
        "dispatch registry must exactly cover release-critical workflows from pins-v1.json",
    )
    require(LOCK_PATH in normalized, "canonical uv-lock workflow missing from dispatch registry")

    return {
        "status": "PASS",
        "workflow_count": len(normalized),
        "release_critical_paths": sorted(normalized),
        "modes": dict(sorted(normalized.items())),
    }


def validate_local_release_workflows(result: Mapping[str, Any]) -> None:
    paths = result.get("release_critical_paths")
    require(isinstance(paths, list), "normalized dispatch registry result malformed")
    for raw in paths:
        require(isinstance(raw, str), "normalized dispatch registry path must be a string")
        path = ROOT / raw
        require(path.is_file(), f"release-ref workflow missing: {raw}")
        source = path.read_text(encoding="utf-8")
        require("workflow_dispatch:" in source, f"release-critical workflow lost workflow_dispatch: {raw}")
        require("  registry-only:\n" not in source, f"release-ref workflow must not be a default-branch registry stub: {raw}")
        require("Default-branch registry only" not in source, f"release-ref workflow must not contain registry-only execution text: {raw}")

    lock_source = (ROOT / LOCK_PATH).read_text(encoding="utf-8")
    for marker in (
        "  regenerate-lock:\n",
        "  commit-lock:\n",
        "permissions:\n  contents: read\n",
        "permissions:\n      contents: write\n",
        "REGENERATE_NODE73_UV_LOCK",
        "uv lock\n",
        "uv sync --all-packages --frozen",
        "git add -- uv.lock",
    ):
        require(marker in lock_source, f"release-ref canonical uv-lock workflow missing hardened marker {marker!r}")


def self_test() -> dict[str, Any]:
    pins = {
        "release_critical_workflows": [
            ".github/workflows/a.yml",
            LOCK_PATH,
            ".github/workflows/b.yml",
        ]
    }
    clean = {
        "schema_version": 1,
        "policy": EXPECTED_POLICY,
        "repository": EXPECTED_REPOSITORY,
        "default_branch": EXPECTED_DEFAULT_BRANCH,
        "release_ref": EXPECTED_RELEASE_REF,
        "registry_behavior": "DEFAULT_BRANCH_DISCOVERY_ONLY_RELEASE_REF_EXECUTION",
        "workflows": [
            {"path": ".github/workflows/a.yml", "default_branch_mode": STUB_MODE},
            {"path": LOCK_PATH, "default_branch_mode": STUB_MODE},
            {"path": ".github/workflows/b.yml", "default_branch_mode": STUB_MODE},
        ],
    }
    normalized = normalize_registry(clean, pins)
    require(normalized.get("workflow_count") == 3, "clean dispatch registry fixture did not normalize")

    mutations: list[dict[str, Any]] = []
    missing = deepcopy(clean)
    missing["workflows"].pop()
    mutations.append(missing)
    duplicate = deepcopy(clean)
    duplicate["workflows"].append(deepcopy(duplicate["workflows"][0]))
    mutations.append(duplicate)
    privileged_mode = deepcopy(clean)
    privileged_mode["workflows"][1]["default_branch_mode"] = "CANONICAL_TWO_PHASE_BOOTSTRAP"
    mutations.append(privileged_mode)
    wrong_branch = deepcopy(clean)
    wrong_branch["default_branch"] = "release-closure-p0"
    mutations.append(wrong_branch)
    wrong_release_ref = deepcopy(clean)
    wrong_release_ref["release_ref"] = "main"
    mutations.append(wrong_release_ref)

    blocked = 0
    for index, mutation in enumerate(mutations, start=1):
        try:
            normalize_registry(mutation, pins)
        except DispatchRegistryContractError:
            blocked += 1
            continue
        raise DispatchRegistryContractError(f"negative dispatch registry drill did not block: {index}")
    return {"status": "PASS", "negative_drills": blocked}


def main() -> int:
    self_result = self_test()
    require(
        self_result.get("status") == "PASS" and self_result.get("negative_drills") == 5,
        "dispatch registry self-test drift",
    )
    result = normalize_registry(load_json(REGISTRY), load_json(PINS))
    validate_local_release_workflows(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DispatchRegistryContractError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release dispatch registry contract failed: {exc}") from exc
