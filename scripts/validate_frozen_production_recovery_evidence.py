#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_SCRIPT = ROOT / "scripts" / "production-recovery-decision.py"
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
EXPECTED_WORKFLOW = "Production DR Rehearsal"
EXPECTED_WORKFLOW_PATH = ".github/workflows/production-dr-rehearsal.yml"
EXPECTED_BRANCH = "release-closure-p0"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_NAMES = (
    "baseline-runtime.json",
    "rds-restore.json",
    "database-verify.json",
    "object-recovery.json",
    "cleanup.json",
)


class FrozenRecoveryError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FrozenRecoveryError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrozenRecoveryError(f"unable to read {label}: {path}") from exc
    require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def normalize_sha(value: object, label: str) -> str:
    require(isinstance(value, str) and SHA40.fullmatch(value) is not None, f"{label} must be lowercase SHA40")
    return value


def positive_int(value: object, label: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool) and value > 0, f"{label} must be positive integer")
    return value


def git_is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def validate_source_run_static(run: Mapping[str, Any]) -> dict[str, Any]:
    require(run.get("repository") == EXPECTED_REPOSITORY, "recovery producer repository mismatch")
    require(run.get("name") == EXPECTED_WORKFLOW, "recovery producer workflow name mismatch")
    require(run.get("path") == EXPECTED_WORKFLOW_PATH, "recovery producer workflow path mismatch")
    require(run.get("event") == "workflow_dispatch", "recovery producer event must be workflow_dispatch")
    require(run.get("status") == "completed", "recovery producer run must be completed")
    require(run.get("conclusion") == "success", "recovery producer run must conclude success")
    require(run.get("head_branch") == EXPECTED_BRANCH, "recovery producer head branch mismatch")
    head_sha = normalize_sha(run.get("head_sha"), "recovery producer head_sha")
    run_id = positive_int(run.get("id"), "recovery producer run id")
    attempt = positive_int(run.get("run_attempt"), "recovery producer run attempt")
    expected_url = f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/{run_id}"
    require(run.get("html_url") == expected_url, "recovery producer run URL mismatch")
    updated_at = run.get("updated_at")
    require(isinstance(updated_at, str) and bool(updated_at.strip()), "recovery producer updated_at missing")
    return {
        "run_id": run_id,
        "run_attempt": attempt,
        "head_sha": head_sha,
        "head_branch": EXPECTED_BRANCH,
        "workflow": EXPECTED_WORKFLOW,
        "workflow_path": EXPECTED_WORKFLOW_PATH,
    }


def validate_bundle(
    *,
    decision_path: Path,
    source_run_path: Path,
    manifest_path: Path,
    expected_evidence_head: str | None,
    verify_git: bool,
) -> dict[str, Any]:
    decision_path = decision_path.resolve()
    source_run_path = source_run_path.resolve()
    manifest_path = manifest_path.resolve()
    decision = load(decision_path, "recovery decision")
    source_run = load(source_run_path, "recovery source run")
    manifest = load(manifest_path, "Production manifest")

    deployment_id = manifest.get("deployment_id")
    require(isinstance(deployment_id, str) and bool(deployment_id), "manifest deployment_id missing")
    expected_manifest = (ROOT / "reports" / "production-deployments" / deployment_id / "manifest.json").resolve()
    expected_dir = (ROOT / "reports" / "production-recovery" / deployment_id).resolve()
    require(manifest_path == expected_manifest, "recovery manifest path is not canonical")
    require(decision_path == expected_dir / "decision.json", "recovery decision path is not canonical")
    require(source_run_path == expected_dir / "source-run.json", "recovery source-run path is not canonical")

    rc = manifest.get("release_candidate")
    require(isinstance(rc, Mapping), "manifest release_candidate missing")
    rc_sha = normalize_sha(rc.get("git_sha"), "manifest Source RC SHA")
    require(decision.get("deployment_id") == deployment_id, "recovery decision deployment_id mismatch")
    decision_rc = decision.get("release_candidate")
    require(isinstance(decision_rc, Mapping) and decision_rc.get("git_sha") == rc_sha, "recovery decision Source RC mismatch")
    require(decision.get("passed") is True, "frozen recovery decision must pass")

    producer = validate_source_run_static(source_run)
    producer_head = producer["head_sha"]
    if expected_evidence_head is not None:
        evidence_head = normalize_sha(expected_evidence_head, "expected Evidence Head")
    else:
        evidence_head = None
    if verify_git:
        require(git_is_ancestor(rc_sha, producer_head), "Source RC is not ancestor of recovery producer Evidence Head")
        if evidence_head is not None:
            require(git_is_ancestor(producer_head, evidence_head), "recovery producer head is not ancestor of freeze Evidence Head")

    evidence_dir = expected_dir / "evidence"
    expected_files = [evidence_dir / name for name in EVIDENCE_NAMES]
    for path in expected_files:
        require(path.is_file(), f"frozen recovery evidence missing: {path.relative_to(ROOT)}")
    actual_files = sorted(path for path in expected_dir.rglob("*") if path.is_file())
    expected_all = sorted([decision_path, source_run_path, *expected_files])
    require(actual_files == expected_all, "frozen recovery directory must contain exactly decision, source-run, and five evidence files")

    module = load_module(DECISION_SCRIPT, "lumi_frozen_production_recovery_decision")
    recomputed = module.evaluate(
        manifest,
        load(expected_files[0], EVIDENCE_NAMES[0]),
        load(expected_files[1], EVIDENCE_NAMES[1]),
        load(expected_files[2], EVIDENCE_NAMES[2]),
        load(expected_files[3], EVIDENCE_NAMES[3]),
        load(expected_files[4], EVIDENCE_NAMES[4]),
        [module.freeze(path) for path in expected_files],
    )
    require(recomputed == decision, "frozen recovery decision differs from canonical recomputation")

    refs = decision.get("evidence_refs")
    require(isinstance(refs, list) and len(refs) == 5, "recovery decision must bind exactly five raw evidence refs")
    return {
        "schema_version": 1,
        "kind": "LUMI_FROZEN_PRODUCTION_RECOVERY_EVIDENCE_V2",
        "status": "PASS",
        "deployment_id": deployment_id,
        "source_rc_sha": rc_sha,
        "producer_run_id": producer["run_id"],
        "producer_run_attempt": producer["run_attempt"],
        "producer_head_sha": producer_head,
        "evidence_head_sha": evidence_head,
        "evidence_ref_count": 5,
        "file_count": 7,
    }


def self_test() -> dict[str, Any]:
    clean = {
        "repository": EXPECTED_REPOSITORY,
        "id": 123,
        "name": EXPECTED_WORKFLOW,
        "path": EXPECTED_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": EXPECTED_BRANCH,
        "head_sha": "a" * 40,
        "run_attempt": 1,
        "updated_at": "2026-08-20T00:00:00Z",
        "html_url": f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/123",
    }
    validate_source_run_static(clean)
    mutations = (
        ("repository", "attacker/repo"),
        ("name", "Fake DR"),
        ("path", ".github/workflows/fake.yml"),
        ("event", "push"),
        ("conclusion", "failure"),
        ("head_branch", "main"),
        ("head_sha", "bad"),
        ("html_url", "https://example.invalid/run/123"),
    )
    blocked = 0
    for key, value in mutations:
        bad = dict(clean)
        bad[key] = value
        try:
            validate_source_run_static(bad)
        except FrozenRecoveryError:
            blocked += 1
            continue
        raise FrozenRecoveryError(f"negative recovery provenance drill did not block: {key}")
    require(blocked == 8, "recovery provenance negative drill count drift")
    return {"status": "PASS", "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate frozen Production recovery evidence and V2 producer provenance")
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--expected-evidence-head")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            print(json.dumps(self_test(), sort_keys=True))
            return 0
        require(args.decision is not None and args.source_run is not None and args.manifest is not None, "--decision/--source-run/--manifest are required")
        result = validate_bundle(
            decision_path=args.decision,
            source_run_path=args.source_run,
            manifest_path=args.manifest,
            expected_evidence_head=args.expected_evidence_head,
            verify_git=True,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (FrozenRecoveryError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"frozen Production recovery evidence blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
