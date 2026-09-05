#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_REQUIRED_SERVICES = ("api", "agent-runtime", "tool-gateway", "sandbox-runtime")


class RuntimeIdentityError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeIdentityError(message)


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeIdentityError(f"unable to read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeIdentityError(f"{label} must be a JSON object")
    return payload


def validate_runtime_identity(
    staging: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    release = staging.get("release_candidate")
    image_set = staging.get("container_image_set")
    _require(isinstance(release, dict), "staging release_candidate is missing")
    _require(isinstance(image_set, dict), "staging container_image_set is missing")
    assert isinstance(release, dict)
    assert isinstance(image_set, dict)

    git_sha = release.get("git_sha")
    _require(
        isinstance(git_sha, str) and bool(_SHA40.fullmatch(git_sha)),
        "staging release_candidate.git_sha must be a full SHA",
    )
    _require(runtime.get("environment") == "staging", "runtime environment must be staging")
    _require(runtime.get("synthetic_only") is True, "runtime identity must be synthetic_only=true")
    _require(runtime.get("release_git_sha") == git_sha, "runtime release SHA differs from staging RC")
    _require(runtime.get("cluster") == "lumi-staging-cluster", "runtime cluster is not canonical staging")

    expected_images = image_set.get("images")
    runtime_services = runtime.get("services")
    _require(isinstance(expected_images, dict), "staging image set is missing images")
    _require(isinstance(runtime_services, dict), "runtime identity is missing services")
    assert isinstance(expected_images, dict)
    assert isinstance(runtime_services, dict)

    verified: dict[str, str] = {}
    for service in _REQUIRED_SERVICES:
        expected = expected_images.get(service)
        _require(
            isinstance(expected, str) and bool(_IMAGE.fullmatch(expected)),
            f"staging {service} image must be digest-pinned",
        )
        row = runtime_services.get(service)
        _require(isinstance(row, dict), f"runtime identity is missing {service}")
        assert isinstance(row, dict)
        actual = row.get("image")
        _require(
            isinstance(actual, str) and bool(_IMAGE.fullmatch(actual)),
            f"deployed {service} image must be digest-pinned",
        )
        _require(actual == expected, f"deployed {service} image differs from staging RC")
        _require(row.get("image_is_immutable") is True, f"{service} image identity is not immutable")
        _require(row.get("assign_public_ip") == "DISABLED", f"{service} must disable public IPs")
        _require(
            isinstance(row.get("subnet_count"), int) and row["subnet_count"] > 0,
            f"{service} must run in deployed private subnets",
        )
        _require(
            isinstance(row.get("security_group_count"), int) and row["security_group_count"] > 0,
            f"{service} must reuse deployed security groups",
        )
        task_definition = row.get("task_definition")
        _require(
            isinstance(task_definition, str) and bool(task_definition),
            f"{service} task definition is missing",
        )
        verified[service] = actual

    return {
        "schema_version": 1,
        "status": "PASS",
        "environment": "staging",
        "release_git_sha": git_sha,
        "cluster": "lumi-staging-cluster",
        "synthetic_only": True,
        "verified_images": verified,
        "service_count": len(verified),
    }


def _fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    sha = "a" * 40
    images = {
        service: f"registry/{service}@sha256:{str(index) * 64}"
        for index, service in enumerate(_REQUIRED_SERVICES, start=1)
    }
    staging = {
        "release_candidate": {"git_sha": sha, "version": "rc-test"},
        "container_image_set": {"images": images},
    }
    runtime = {
        "schema_version": 1,
        "environment": "staging",
        "release_git_sha": sha,
        "cluster": "lumi-staging-cluster",
        "synthetic_only": True,
        "services": {
            service: {
                "image": image,
                "image_is_immutable": True,
                "assign_public_ip": "DISABLED",
                "subnet_count": 2,
                "security_group_count": 2,
                "task_definition": f"arn:aws:ecs:region:account:task-definition/lumi-staging-{service}:1",
            }
            for service, image in images.items()
        },
    }
    return staging, runtime


def _must_fail(label: str, staging: dict[str, Any], runtime: dict[str, Any]) -> None:
    try:
        validate_runtime_identity(staging, runtime)
    except RuntimeIdentityError:
        return
    raise RuntimeError(f"runtime identity self-test accepted invalid evidence: {label}")


def self_test() -> None:
    staging, runtime = _fixture()
    result = validate_runtime_identity(staging, runtime)
    _require(result["service_count"] == 4, "self-test service count mismatch")

    bad = copy.deepcopy(runtime)
    bad["release_git_sha"] = "b" * 40
    _must_fail("wrong release SHA", staging, bad)

    bad = copy.deepcopy(runtime)
    bad["services"]["tool-gateway"]["image"] = f"registry/tool-gateway@sha256:{'f' * 64}"
    _must_fail("wrong Tool Gateway image", staging, bad)

    bad = copy.deepcopy(runtime)
    bad["services"]["sandbox-runtime"]["assign_public_ip"] = "ENABLED"
    _must_fail("public sandbox runtime", staging, bad)

    bad = copy.deepcopy(runtime)
    del bad["services"]["agent-runtime"]
    _must_fail("missing Agent Runtime", staging, bad)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("Tool Gateway P0 runtime identity contract: PASS")
        return 0
    if args.staging is None or args.runtime is None:
        raise SystemExit("--staging and --runtime are required unless --self-test is used")
    try:
        result = validate_runtime_identity(
            _load(args.staging, "staging evidence"),
            _load(args.runtime, "Tool Gateway runtime identity"),
        )
    except RuntimeIdentityError as exc:
        raise SystemExit(f"Tool Gateway P0 runtime identity failed: {exc}") from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
