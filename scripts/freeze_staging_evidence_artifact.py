#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
KIND = "LUMI_STAGING_EVIDENCE_ARTIFACT_V1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
WORKFLOW_PATH = re.compile(r"^\.github/workflows/[A-Za-z0-9._/-]+\.ya?ml$")


class FreezeError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FreezeError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"unable to read {label}: {path}") from exc
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def validate_source_run(run: Mapping[str, Any]) -> dict[str, Any]:
    require(run.get("repository") == EXPECTED_REPOSITORY, "collector repository mismatch")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "collector run must complete successfully")
    run_id = run.get("id")
    attempt = run.get("run_attempt")
    require(isinstance(run_id, int) and run_id > 0, "collector run id is invalid")
    require(isinstance(attempt, int) and attempt > 0, "collector run attempt is invalid")
    workflow = run.get("name")
    path = run.get("path")
    head_sha = run.get("head_sha")
    head_branch = run.get("head_branch")
    html_url = run.get("html_url")
    require(isinstance(workflow, str) and bool(workflow.strip()), "collector workflow name is missing")
    require(isinstance(path, str) and bool(WORKFLOW_PATH.fullmatch(path)), "collector workflow path is invalid")
    require(isinstance(head_sha, str) and bool(SHA40.fullmatch(head_sha.lower())), "collector head SHA is invalid")
    require(isinstance(head_branch, str) and bool(head_branch.strip()), "collector head branch is missing")
    expected_url = f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/{run_id}"
    require(html_url == expected_url, "collector run URL mismatch")
    captured_at = run.get("updated_at")
    require(isinstance(captured_at, str) and bool(captured_at.strip()), "collector updated_at is missing")
    return {
        "repository": EXPECTED_REPOSITORY,
        "workflow": workflow,
        "workflow_path": path,
        "run_id": run_id,
        "run_attempt": attempt,
        "run_url": expected_url,
        "head_sha": head_sha.lower(),
        "head_branch": head_branch,
        "captured_at": captured_at,
    }


def freeze(*, artifact_id: str, rc_sha: str, validation: Mapping[str, Any], source_run: Mapping[str, Any], raw_evidence: Mapping[str, Any]) -> dict[str, Any]:
    require(bool(artifact_id.strip()), "artifact id is required")
    require(all(ord(char) >= 32 and ord(char) != 127 for char in artifact_id), "artifact id contains control characters")
    require(isinstance(rc_sha, str) and bool(SHA40.fullmatch(rc_sha)), "RC SHA must be lowercase SHA40")
    require(validation.get("status") == "PASS", "freeze input validation must PASS")
    require(validation.get("release_git_sha") == rc_sha, "validation release Git SHA mismatch")
    raw_rc = raw_evidence.get("release_candidate")
    require(isinstance(raw_rc, Mapping) and raw_rc.get("git_sha") == rc_sha, "raw evidence release Git SHA mismatch")
    producer = validate_source_run(source_run)
    raw_bytes = (json.dumps(raw_evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    return {
        "schema_version": 1,
        "kind": KIND,
        "artifact_id": artifact_id,
        "status": "PASS",
        "rc_git_sha": rc_sha,
        "captured_at": producer.pop("captured_at"),
        "producer": producer,
        "payload": {
            "validation": dict(validation),
            "raw_evidence_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "raw_evidence": dict(raw_evidence),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze a validated Staging collector result into the canonical evidence wrapper")
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--rc-sha", required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--raw-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        wrapper = freeze(
            artifact_id=args.artifact_id,
            rc_sha=args.rc_sha,
            validation=load(args.validation, "validation"),
            source_run=load(args.source_run, "source run"),
            raw_evidence=load(args.raw_evidence, "raw evidence"),
        )
        output = args.output.resolve()
        root = Path.cwd().resolve()
        allowed = (root / "reports" / "staging-acceptance" / "evidence").resolve()
        try:
            output.relative_to(allowed)
        except ValueError as exc:
            raise FreezeError("output must stay below reports/staging-acceptance/evidence/") from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(wrapper, indent=2, sort_keys=True) + "\n"
        output.write_text(encoded, encoding="utf-8")
        sha = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        catalog = {
            args.artifact_id: {
                "path": output.relative_to(root).as_posix(),
                "sha256": sha,
                "rc_git_sha": args.rc_sha,
            }
        }
        args.catalog_output.parent.mkdir(parents=True, exist_ok=True)
        args.catalog_output.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "PASS", "artifact_id": args.artifact_id, "sha256": sha}, sort_keys=True))
        return 0
    except FreezeError as exc:
        raise SystemExit(f"staging evidence freeze blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
