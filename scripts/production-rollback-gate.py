#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SHA40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
REQUIRED_IMAGES = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}


class RollbackGateError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RollbackGateError(f"{path} must contain a JSON object")
    return payload


def present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def rc_identity(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    rc = payload.get("release_candidate")
    if not isinstance(rc, dict):
        return None, None, None
    return rc.get("git_sha"), rc.get("version"), rc.get("migration_head")


def validate_manifest(payload: dict[str, Any], *, label: str) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_version") != 1:
        blockers.append(f"{label} schema_version must be 1")
    if payload.get("environment") != "production":
        blockers.append(f"{label} environment must be production")
    if not present(payload.get("deployment_id")):
        blockers.append(f"{label} deployment_id missing/PENDING")
    sha, version, migration = rc_identity(payload)
    if not isinstance(sha, str) or not SHA40.fullmatch(sha.lower()):
        blockers.append(f"{label} release_candidate.git_sha must be SHA40")
    if not present(version):
        blockers.append(f"{label} release_candidate.version missing/PENDING")
    if not present(migration):
        blockers.append(f"{label} release_candidate.migration_head missing/PENDING")
    images = payload.get("images")
    if not isinstance(images, dict) or set(images) != REQUIRED_IMAGES:
        blockers.append(f"{label} images must contain exactly the canonical six runtimes")
    elif any(not isinstance(value, str) or not DIGEST_IMAGE.fullmatch(value) for value in images.values()):
        blockers.append(f"{label} images must all use immutable @sha256 digests")
    return blockers


def evaluate(
    current: dict[str, Any],
    previous: dict[str, Any],
    previous_path: Path,
) -> dict[str, Any]:
    blockers = validate_manifest(current, label="current")
    blockers.extend(validate_manifest(previous, label="previous"))

    current_rollback = current.get("rollback")
    if not isinstance(current_rollback, dict):
        blockers.append("current rollback object missing")
        current_rollback = {}

    if current_rollback.get("database_backward_compatible") is not True:
        blockers.append("current rollback.database_backward_compatible must be explicitly true")
    if current_rollback.get("previous_deployment_id") != previous.get("deployment_id"):
        blockers.append("rollback previous_deployment_id does not match previous manifest")
    configured_previous = current_rollback.get("previous_manifest_ref")
    if not present(configured_previous):
        blockers.append("rollback previous_manifest_ref missing/PENDING")
    elif Path(str(configured_previous)).as_posix() != previous_path.as_posix():
        blockers.append("rollback previous_manifest_ref does not match evaluated previous manifest path")

    for section, keys in (
        ("aws", ("account_id", "region", "production_role_arn")),
        ("edge", ("domain", "certificate_arn")),
    ):
        current_section = current.get(section)
        previous_section = previous.get(section)
        if not isinstance(current_section, dict) or not isinstance(previous_section, dict):
            blockers.append(f"{section} object missing from current/previous manifest")
            continue
        for key in keys:
            if current_section.get(key) != previous_section.get(key):
                blockers.append(f"rollback cannot cross {section}.{key}")

    if current.get("deployment_id") == previous.get("deployment_id"):
        blockers.append("rollback target must be a distinct deployment")
    if current.get("images") == previous.get("images"):
        blockers.append("rollback target must change at least one runtime image digest")

    current_sha, current_version, current_migration = rc_identity(current)
    previous_sha, previous_version, previous_migration = rc_identity(previous)
    payload = {
        "schema_version": 1,
        "current_deployment_id": current.get("deployment_id"),
        "previous_deployment_id": previous.get("deployment_id"),
        "current_release_candidate": {
            "git_sha": current_sha,
            "version": current_version,
            "migration_head": current_migration,
        },
        "previous_release_candidate": {
            "git_sha": previous_sha,
            "version": previous_version,
            "migration_head": previous_migration,
        },
        "current_images": current.get("images", {}),
        "previous_images": previous.get("images", {}),
        "database_backward_compatible": current_rollback.get("database_backward_compatible"),
        "passed": not blockers,
        "blockers": sorted(set(blockers)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {"gate_id": hashlib.sha256(canonical.encode()).hexdigest()[:24], **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate a production application rollback rehearsal")
    parser.add_argument("--current-manifest", required=True)
    parser.add_argument("--previous-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        current_path = Path(args.current_manifest)
        previous_path = Path(args.previous_manifest)
        result = evaluate(load_json(current_path), load_json(previous_path), previous_path)
    except (OSError, json.JSONDecodeError, RollbackGateError) as exc:
        raise SystemExit(f"production rollback gate invalid: {exc}") from exc
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if result["passed"] else "BLOCK", "gate_id": result["gate_id"]}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
