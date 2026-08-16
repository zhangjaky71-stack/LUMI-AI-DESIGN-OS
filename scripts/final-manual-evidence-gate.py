#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"^[0-9a-f]{64}$")
P0_MANUAL_SCENARIOS = (
    "UAT-01",
    "BILLING-UX-01",
    "BROWSER-01",
    "BROWSER-02",
    "A11Y-01",
)
OPTIONAL_MANUAL_SCENARIOS = ("RESPONSIVE-01",)

REQUIRED_CHECKS: dict[str, set[str]] = {
    "UAT-01": {
        "project",
        "agent",
        "generation",
        "canvas",
        "artifact-version",
        "export",
        "error-retry-reconnect",
    },
    "BILLING-UX-01": {
        "plan-display",
        "authorization",
        "checkout",
        "success-cancel",
        "portal",
        "cancellation",
        "idempotency",
        "csrf-origin",
        "error-states",
    },
}

REQUIRED_BROWSERS: dict[str, set[str]] = {
    "BROWSER-01": {"chrome", "edge"},
    "BROWSER-02": {"safari", "firefox"},
}

REQUIRED_A11Y_MANUAL = {
    "keyboard",
    "focus",
    "semantics",
    "contrast",
    "screen-reader",
}


class ManualEvidenceError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ManualEvidenceError(f"{path} must contain a JSON object")
    return payload


def present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def parse_utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ManualEvidenceError(f"{label} must be an ISO-8601 UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ManualEvidenceError(f"{label} must be an ISO-8601 UTC Z timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ManualEvidenceError(f"{label} must be UTC")
    return parsed


def repo_file(value: str, *, allowed_prefixes: tuple[str, ...]) -> Path:
    path = (ROOT / value).resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ManualEvidenceError(f"path escapes repository: {value}") from exc
    if not any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in allowed_prefixes):
        raise ManualEvidenceError(f"path outside allowed evidence roots: {value}")
    if not path.is_file():
        raise ManualEvidenceError(f"evidence file missing: {value}")
    return path


def verify_ref(ref: Any, *, label: str, allowed_prefixes: tuple[str, ...]) -> Path:
    if not isinstance(ref, dict):
        raise ManualEvidenceError(f"{label} must be an object")
    path_value = ref.get("path")
    hash_value = ref.get("sha256")
    if not present(path_value):
        raise ManualEvidenceError(f"{label}.path is missing/PENDING")
    if not isinstance(hash_value, str) or not SHA256.fullmatch(hash_value.lower()):
        raise ManualEvidenceError(f"{label}.sha256 must be exact SHA-256")
    path = repo_file(str(path_value), allowed_prefixes=allowed_prefixes)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != hash_value.lower():
        raise ManualEvidenceError(
            f"{label} SHA mismatch: expected {hash_value.lower()}, got {actual}"
        )
    return path


def rc_identity(payload: dict[str, Any]) -> tuple[Any, Any, Any]:
    rc = payload.get("release_candidate")
    if not isinstance(rc, dict):
        return None, None, None
    return rc.get("git_sha"), rc.get("version"), rc.get("migration_head")


def scenario_items(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = evidence.get("items")
    if not isinstance(items, list):
        raise ManualEvidenceError("acceptance evidence items must be an array")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ManualEvidenceError("acceptance evidence contains invalid item")
        result[item["id"]] = item
    return result


def find_manual_record(
    *,
    release_id: str,
    scenario_id: str,
    item: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    refs = item.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        raise ManualEvidenceError(f"{scenario_id} has no evidence_refs")
    expected_prefix = f"reports/final-acceptance/{release_id}/manual/"
    candidates = [
        ref
        for ref in refs
        if isinstance(ref, dict)
        and isinstance(ref.get("path"), str)
        and ref["path"].startswith(expected_prefix)
        and ref["path"].endswith(".json")
    ]
    if len(candidates) != 1:
        raise ManualEvidenceError(
            f"{scenario_id} requires exactly one structured manual JSON under {expected_prefix}"
        )
    path = verify_ref(
        candidates[0],
        label=f"{scenario_id}.manual_record",
        allowed_prefixes=("reports/final-acceptance/",),
    )
    return load_json(path), path


def validate_common(
    *,
    record: dict[str, Any],
    release: dict[str, Any],
    scenario_id: str,
) -> list[str]:
    blockers: list[str] = []
    if record.get("schema_version") != 1:
        blockers.append(f"{scenario_id}: manual record schema_version must be 1")
    if record.get("release_id") != release.get("release_id"):
        blockers.append(f"{scenario_id}: manual record release_id mismatch")
    if record.get("scenario_id") != scenario_id:
        blockers.append(f"{scenario_id}: manual record scenario_id mismatch")
    if record.get("status") != "PASS":
        blockers.append(f"{scenario_id}: manual record status must be PASS")
    if rc_identity(record) != rc_identity(release):
        blockers.append(f"{scenario_id}: manual record RC identity mismatch")
    for field in ("environment", "tester"):
        if not present(record.get(field)):
            blockers.append(f"{scenario_id}: {field} is missing/PENDING")
    try:
        started = parse_utc(record.get("started_at_utc"), label=f"{scenario_id}.started_at_utc")
        completed = parse_utc(
            record.get("completed_at_utc"), label=f"{scenario_id}.completed_at_utc"
        )
        if completed < started:
            blockers.append(f"{scenario_id}: completed_at_utc precedes started_at_utc")
    except ManualEvidenceError as exc:
        blockers.append(str(exc))

    refs = record.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        blockers.append(f"{scenario_id}: manual record requires nested evidence_refs")
    else:
        for index, ref in enumerate(refs):
            try:
                verify_ref(
                    ref,
                    label=f"{scenario_id}.manual.evidence_refs[{index}]",
                    allowed_prefixes=(
                        "reports/",
                        "docs/",
                        "evals/",
                        "staging/",
                        "production/",
                    ),
                )
            except ManualEvidenceError as exc:
                blockers.append(str(exc))
    return blockers


def validate_check_list(record: dict[str, Any], *, scenario_id: str) -> list[str]:
    required = REQUIRED_CHECKS[scenario_id]
    checks = record.get("checks")
    if not isinstance(checks, list):
        return [f"{scenario_id}: checks must be an array"]
    by_id = {
        check.get("id"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("id"), str)
    }
    blockers: list[str] = []
    missing = sorted(required - set(by_id))
    if missing:
        blockers.append(f"{scenario_id}: missing required checks {missing}")
    for check_id in sorted(required & set(by_id)):
        if by_id[check_id].get("status") != "PASS":
            blockers.append(f"{scenario_id}: check {check_id} must PASS")
    return blockers


def validate_browser_record(record: dict[str, Any], *, scenario_id: str) -> list[str]:
    required = REQUIRED_BROWSERS[scenario_id]
    clients = record.get("clients")
    if not isinstance(clients, list):
        return [f"{scenario_id}: clients must be an array"]
    by_browser = {
        client.get("browser"): client
        for client in clients
        if isinstance(client, dict) and isinstance(client.get("browser"), str)
    }
    blockers: list[str] = []
    missing = sorted(required - set(by_browser))
    if missing:
        blockers.append(f"{scenario_id}: missing required real browsers {missing}")
    for browser in sorted(required & set(by_browser)):
        client = by_browser[browser]
        if client.get("status") != "PASS":
            blockers.append(f"{scenario_id}: {browser} must PASS")
        if client.get("real_browser") is not True:
            blockers.append(f"{scenario_id}: {browser} must be real_browser=true")
        for field in ("browser_version", "os", "os_version"):
            if not present(client.get(field)):
                blockers.append(f"{scenario_id}: {browser}.{field} missing/PENDING")
        if browser == "safari" and client.get("engine_preflight_only") is True:
            blockers.append(
                "BROWSER-02: Safari cannot be satisfied by WebKit engine_preflight_only evidence"
            )
    return blockers


def validate_a11y(record: dict[str, Any]) -> list[str]:
    checks = record.get("manual_checks")
    if not isinstance(checks, list):
        return ["A11Y-01: manual_checks must be an array"]
    by_id = {
        check.get("id"): check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("id"), str)
    }
    blockers: list[str] = []
    missing = sorted(REQUIRED_A11Y_MANUAL - set(by_id))
    if missing:
        blockers.append(f"A11Y-01: missing required manual checks {missing}")
    for check_id in sorted(REQUIRED_A11Y_MANUAL & set(by_id)):
        if by_id[check_id].get("status") != "PASS":
            blockers.append(f"A11Y-01: manual check {check_id} must PASS")
    screen_reader = by_id.get("screen-reader")
    if isinstance(screen_reader, dict):
        if not present(screen_reader.get("assistive_technology")):
            blockers.append("A11Y-01: screen-reader assistive_technology missing/PENDING")
        if not present(screen_reader.get("assistive_technology_version")):
            blockers.append("A11Y-01: screen-reader assistive_technology_version missing/PENDING")
    return blockers


def evaluate(release: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    release_id = release.get("release_id")
    if not present(release_id):
        blockers.append("release_id missing/PENDING")
        release_id = "PENDING"
    if evidence.get("release_id") != release.get("release_id"):
        blockers.append("acceptance evidence release_id mismatch")
    if rc_identity(evidence) != rc_identity(release):
        blockers.append("acceptance evidence RC identity mismatch")

    try:
        items = scenario_items(evidence)
    except ManualEvidenceError as exc:
        return {"schema_version": 1, "passed": False, "blockers": [str(exc)]}

    scenarios = list(P0_MANUAL_SCENARIOS)
    responsive = items.get("RESPONSIVE-01")
    if isinstance(responsive, dict) and responsive.get("status") == "PASS":
        scenarios.extend(OPTIONAL_MANUAL_SCENARIOS)

    for scenario_id in scenarios:
        item = items.get(scenario_id)
        if item is None:
            blockers.append(f"{scenario_id}: acceptance item missing")
            continue
        if item.get("status") != "PASS":
            blockers.append(f"{scenario_id}: structured manual gate requires PASS")
            continue
        try:
            record, _ = find_manual_record(
                release_id=str(release_id), scenario_id=scenario_id, item=item
            )
        except (ManualEvidenceError, OSError, json.JSONDecodeError) as exc:
            blockers.append(str(exc))
            continue
        blockers.extend(validate_common(record=record, release=release, scenario_id=scenario_id))
        if scenario_id in REQUIRED_CHECKS:
            blockers.extend(validate_check_list(record, scenario_id=scenario_id))
        if scenario_id in REQUIRED_BROWSERS:
            blockers.extend(validate_browser_record(record, scenario_id=scenario_id))
        if scenario_id == "A11Y-01":
            blockers.extend(validate_a11y(record))
        if scenario_id == "RESPONSIVE-01":
            clients = record.get("clients")
            if not isinstance(clients, list) or not clients:
                blockers.append("RESPONSIVE-01: PASS requires at least one tested client/device")
            else:
                for index, client in enumerate(clients):
                    if not isinstance(client, dict) or client.get("status") != "PASS":
                        blockers.append(f"RESPONSIVE-01: clients[{index}] must PASS")

    blockers = sorted(set(blockers))
    canonical = json.dumps(
        {
            "release_id": release.get("release_id"),
            "release_candidate": release.get("release_candidate", {}),
            "blockers": blockers,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": 1,
        "decision_id": hashlib.sha256(canonical.encode()).hexdigest()[:24],
        "release_id": release.get("release_id"),
        "release_candidate": release.get("release_candidate", {}),
        "passed": not blockers,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate structured NODE-73 manual UAT evidence")
    parser.add_argument("--release", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        release_path = repo_file(args.release, allowed_prefixes=("reports/final-acceptance/",))
        evidence_path = repo_file(args.evidence, allowed_prefixes=("reports/final-acceptance/",))
        result = evaluate(load_json(release_path), load_json(evidence_path))
    except (OSError, json.JSONDecodeError, ManualEvidenceError) as exc:
        raise SystemExit(f"manual evidence input invalid: {exc}") from exc

    output = (ROOT / args.output).resolve()
    try:
        relative = output.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise SystemExit("manual evidence output escapes repository") from exc
    if not relative.startswith("reports/final-acceptance/"):
        raise SystemExit("manual evidence output must be under reports/final-acceptance/")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "decision_id": result["decision_id"]}))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
