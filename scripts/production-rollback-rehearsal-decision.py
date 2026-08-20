#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_GATE_PATH = ROOT / "scripts" / "production-rollback-gate.py"
RUNTIME_IMAGE_KEYS = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}
RUNTIME_SERVICE_IMAGE_KEY = {
    "api": "api",
    "agent-runtime": "agent-runtime",
    "model-gateway": "model-gateway",
    "tool-gateway": "tool-gateway",
    "worker-media": "worker-media",
    "outbox-dispatcher": "worker-media",
    "sandbox-runtime": "sandbox-runtime",
}


class RollbackDecisionError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RollbackDecisionError(f"{path} must contain a JSON object")
    return payload


def load_rollback_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_production_rollback_gate", ROLLBACK_GATE_PATH)
    if spec is None or spec.loader is None:
        raise RollbackDecisionError("unable to import production rollback gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise RollbackDecisionError(f"evidence path escapes repository: {path}") from exc


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_ref(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RollbackDecisionError(f"evidence file missing: {path}")
    return {"path": repo_path(path), "sha256": digest(path)}


def rc(payload: dict[str, Any], key: str = "release_candidate") -> tuple[Any, Any, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        return None, None, None
    return value.get("git_sha"), value.get("version"), value.get("migration_head")


def _expected_service_images(images: object, blockers: list[str], *, label: str) -> dict[str, str]:
    if not isinstance(images, dict) or set(images) != RUNTIME_IMAGE_KEYS:
        blockers.append(f"{label} manifest must contain exactly six canonical runtime images")
        return {}
    return {
        service: str(images[image_key])
        for service, image_key in RUNTIME_SERVICE_IMAGE_KEY.items()
    }


def _capacity_row_valid(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    expected = item.get("expected_desired_count")
    desired = item.get("desired_count")
    return (
        isinstance(expected, int)
        and not isinstance(expected, bool)
        and expected > 0
        and isinstance(desired, int)
        and not isinstance(desired, bool)
        and desired == expected
        and item.get("capacity_matches") is True
    )


def validate_runtime(
    runtime: dict[str, Any],
    manifest: dict[str, Any],
    *,
    label: str,
    blockers: list[str],
) -> None:
    if runtime.get("schema_version") != 1 or runtime.get("passed") is not True:
        blockers.append(f"{label} runtime identity is not passed=true")
    if runtime.get("deployment_id") != manifest.get("deployment_id"):
        blockers.append(f"{label} runtime deployment_id mismatch")
    if rc(runtime) != rc(manifest):
        blockers.append(f"{label} runtime RC identity mismatch")
    services = runtime.get("services")
    expected_service_images = _expected_service_images(manifest.get("images"), blockers, label=label)
    if not isinstance(services, list) or len(services) != len(RUNTIME_SERVICE_IMAGE_KEY):
        blockers.append(f"{label} runtime must contain exactly seven services")
        return
    observed_images = {
        item.get("service_name"): item.get("image")
        for item in services
        if isinstance(item, dict) and isinstance(item.get("service_name"), str)
    }
    observed_image_keys = {
        item.get("service_name"): item.get("image_key")
        for item in services
        if isinstance(item, dict) and isinstance(item.get("service_name"), str)
    }
    if observed_images != expected_service_images:
        blockers.append(f"{label} seven-service runtime image mapping does not equal manifest")
    if observed_image_keys != RUNTIME_SERVICE_IMAGE_KEY:
        blockers.append(f"{label} runtime service-to-image-key mapping is not canonical")
    if any(
        not isinstance(item, dict)
        or item.get("expected_image") != expected_service_images.get(item.get("service_name"))
        or item.get("image_matches") is not True
        or not _capacity_row_valid(item)
        or item.get("steady") is not True
        for item in services
    ):
        blockers.append(
            f"{label} runtime contains non-steady, image-mismatched, or Terraform-capacity-mismatched service"
        )


def validate_smoke(
    smoke: dict[str, Any],
    manifest: dict[str, Any],
    *,
    label: str,
    blockers: list[str],
) -> None:
    if smoke.get("schema_version") != 1 or smoke.get("passed") is not True:
        blockers.append(f"{label} smoke is not passed=true")
    edge = manifest.get("edge")
    candidate = manifest.get("release_candidate")
    if not isinstance(edge, dict) or not isinstance(candidate, dict):
        blockers.append(f"{label} manifest edge/RC identity missing")
        return
    expected_base = f"https://{edge.get('domain')}"
    if smoke.get("base_url") != expected_base:
        blockers.append(f"{label} smoke base_url mismatch")
    results = smoke.get("results")
    version = results.get("/version") if isinstance(results, dict) else None
    if not isinstance(version, dict) or version.get("version") != candidate.get("version"):
        blockers.append(f"{label} smoke version mismatch")


def evaluate(
    current: dict[str, Any],
    previous: dict[str, Any],
    previous_path: Path,
    previous_runtime: dict[str, Any],
    previous_smoke: dict[str, Any],
    restored_runtime: dict[str, Any],
    restored_smoke: dict[str, Any],
    refs: list[dict[str, str]],
) -> dict[str, Any]:
    gate = load_rollback_gate().evaluate(current, previous, previous_path)
    blockers = list(gate.get("blockers") or [])
    if gate.get("passed") is not True:
        blockers.append("production rollback relationship is not passed=true")
    validate_runtime(previous_runtime, previous, label="rollback-target", blockers=blockers)
    validate_smoke(previous_smoke, previous, label="rollback-target", blockers=blockers)
    validate_runtime(restored_runtime, current, label="roll-forward", blockers=blockers)
    validate_smoke(restored_smoke, current, label="roll-forward", blockers=blockers)

    current_rc = current.get("release_candidate", {})
    previous_rc = previous.get("release_candidate", {})
    blockers = sorted(set(blockers))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "current_deployment_id": current.get("deployment_id"),
        "previous_deployment_id": previous.get("deployment_id"),
        "release_candidate": current_rc,
        "previous_release_candidate": previous_rc,
        "rollback_gate_id": gate.get("gate_id"),
        "rollback_executed": True,
        "roll_forward_restored": not blockers,
        "passed": not blockers,
        "evidence_refs": refs,
        "blockers": blockers,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["decision_id"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize production rollback+roll-forward rehearsal evidence")
    parser.add_argument("--current-manifest", required=True)
    parser.add_argument("--previous-manifest", required=True)
    parser.add_argument("--rollback-gate", required=True)
    parser.add_argument("--previous-runtime", required=True)
    parser.add_argument("--previous-smoke", required=True)
    parser.add_argument("--restored-runtime", required=True)
    parser.add_argument("--restored-smoke", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    current_path = Path(args.current_manifest)
    previous_path = Path(args.previous_manifest)
    gate_path = Path(args.rollback_gate)
    paths = [
        gate_path,
        Path(args.previous_runtime),
        Path(args.previous_smoke),
        Path(args.restored_runtime),
        Path(args.restored_smoke),
    ]
    try:
        current = load_json(current_path)
        previous = load_json(previous_path)
        gate_result = load_rollback_gate().evaluate(current, previous, previous_path)
        gate_path.parent.mkdir(parents=True, exist_ok=True)
        gate_path.write_text(json.dumps(gate_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = evaluate(
            current,
            previous,
            previous_path,
            load_json(paths[1]),
            load_json(paths[2]),
            load_json(paths[3]),
            load_json(paths[4]),
            [evidence_ref(path) for path in paths],
        )
    except (OSError, json.JSONDecodeError, RollbackDecisionError) as exc:
        raise SystemExit(f"production rollback rehearsal decision invalid: {exc}") from exc

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if result["passed"] else "BLOCK", "decision_id": result["decision_id"]}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
