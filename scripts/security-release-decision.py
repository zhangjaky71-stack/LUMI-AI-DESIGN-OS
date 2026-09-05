#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class SecurityDecisionError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SecurityDecisionError(f"{path} must contain a JSON object")
    return payload


def freeze(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise SecurityDecisionError(f"evidence path escapes repository: {path}") from exc
    if not resolved.is_file():
        raise SecurityDecisionError(f"evidence file missing: {path}")
    return {"path": relative, "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest()}


def release_identity(manifest: dict[str, Any]) -> tuple[Any, Any, Any]:
    rc = manifest.get("release_candidate")
    if not isinstance(rc, dict):
        return None, None, None
    return rc.get("git_sha"), rc.get("version"), rc.get("migration_head")


def successful_job(job: dict[str, Any], *, exact_name: str | None = None, prefix: str | None = None) -> bool:
    name = job.get("name")
    if exact_name is not None and name != exact_name:
        return False
    if prefix is not None and (not isinstance(name, str) or not name.startswith(prefix)):
        return False
    steps = job.get("steps")
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        return False
    if not isinstance(steps, list) or not steps:
        return False
    # Zero-execution runner/account failures surface without steps. For real jobs,
    # every non-skipped step must have completed successfully.
    for step in steps:
        if not isinstance(step, dict):
            return False
        conclusion = step.get("conclusion")
        if conclusion not in {"success", "skipped"}:
            return False
    return True


def evaluate(manifest: dict[str, Any], run: dict[str, Any], jobs_payload: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    deployment_id = manifest.get("deployment_id")
    expected_rc = release_identity(manifest)
    git_sha, version, migration_head = expected_rc

    if manifest.get("schema_version") != 1 or manifest.get("environment") != "production":
        blockers.append("manifest must be schema-v1 production")
    if not isinstance(git_sha, str) or not SHA40.fullmatch(git_sha.lower()):
        blockers.append("manifest RC git_sha must be SHA40")
    if not isinstance(version, str) or not version or not isinstance(migration_head, str) or not migration_head:
        blockers.append("manifest RC version/migration_head missing")

    if run.get("name") != "Security Release Gate":
        blockers.append("source run is not Security Release Gate")
    if run.get("event") != "workflow_dispatch":
        blockers.append("security release evidence must come from workflow_dispatch")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        blockers.append("security source run is not completed/success")
    if run.get("head_sha") != git_sha:
        blockers.append("security source run head_sha does not match exact RC")
    if not isinstance(run.get("id"), int):
        blockers.append("security source run id missing")

    jobs = jobs_payload.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        blockers.append("security source run jobs missing")
        jobs = []

    required = ("security-tests", "node-supply-chain", "secret-and-iac-scan", "release-gate")
    for name in required:
        matches = [job for job in jobs if isinstance(job, dict) and job.get("name") == name]
        if len(matches) != 1 or not successful_job(matches[0], exact_name=name):
            blockers.append(f"required security job {name} did not execute to success")

    codeql = [job for job in jobs if isinstance(job, dict) and isinstance(job.get("name"), str) and job["name"].startswith("codeql (")]
    if len(codeql) != 2 or not all(successful_job(job, prefix="codeql (") for job in codeql):
        blockers.append("final security sign-off requires both CodeQL matrix jobs to execute successfully")
    else:
        names = {job.get("name") for job in codeql}
        if not any("javascript-typescript" in str(name) for name in names) or not any("python" in str(name) for name in names):
            blockers.append("CodeQL matrix must cover javascript-typescript and python")

    dependency = [job for job in jobs if isinstance(job, dict) and job.get("name") == "dependency-review"]
    if len(dependency) != 1 or dependency[0].get("conclusion") not in {"skipped", "success"}:
        blockers.append("dependency-review job has an invalid workflow_dispatch outcome")

    blockers = sorted(set(blockers))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "deployment_id": deployment_id,
        "release_candidate": manifest.get("release_candidate", {}),
        "source_workflow": {
            "name": run.get("name"),
            "run_id": run.get("id"),
            "head_sha": run.get("head_sha"),
            "event": run.get("event"),
        },
        "passed": not blockers,
        "blockers": blockers,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["decision_id"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize exact-RC Security Release Gate evidence")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--jobs", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    run_path = Path(args.run)
    jobs_path = Path(args.jobs)
    try:
        result = evaluate(load_json(manifest_path), load_json(run_path), load_json(jobs_path))
        result["evidence_refs"] = [freeze(run_path), freeze(jobs_path)]
    except (OSError, json.JSONDecodeError, SecurityDecisionError) as exc:
        raise SystemExit(f"security release decision invalid: {exc}") from exc
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if result["passed"] else "BLOCK", "decision_id": result["decision_id"]}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
