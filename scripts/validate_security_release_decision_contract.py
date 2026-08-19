#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "scripts/security-release-decision.py"
WORKFLOW = ROOT / ".github/workflows/freeze-security-release-evidence.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"security release decision contract invalid: {message}")


def load_decision() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_security_release_decision", DECISION)
    require(spec is not None and spec.loader is not None, "cannot import security decision")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def step(name: str) -> dict[str, Any]:
    return {"name": name, "status": "completed", "conclusion": "success", "number": 1}


def job(name: str, *, conclusion: str = "success", with_steps: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "steps": [step("real-step")] if with_steps else None,
    }


def fixtures() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    rc = {
        "git_sha": "a" * 40,
        "version": "1.0.0-rc.1",
        "migration_head": "0020_generation_operation_identity",
    }
    manifest = {
        "schema_version": 1,
        "environment": "production",
        "deployment_id": "security-contract-001",
        "release_candidate": rc,
    }
    run = {
        "id": 123456,
        "name": "Security Release Gate",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_sha": rc["git_sha"],
    }
    jobs = {
        "jobs": [
            job("security-tests"),
            job("node-supply-chain"),
            job("codeql (javascript-typescript)"),
            job("codeql (python)"),
            job("dependency-review", conclusion="skipped", with_steps=False),
            job("secret-and-iac-scan"),
            job("release-gate"),
        ]
    }
    return manifest, run, jobs


def evaluate(module: ModuleType, values: tuple[dict[str, Any], dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    return module.evaluate(*values)


def must_block(module: ModuleType, mutate: Callable[[list[dict[str, Any]]], None], label: str) -> None:
    values = [copy.deepcopy(item) for item in fixtures()]
    mutate(values)
    require(evaluate(module, tuple(values))["passed"] is False, f"{label} must block")


def main() -> int:
    module = load_decision()
    clean = fixtures()
    require(evaluate(module, clean)["passed"] is True, "clean security fixture must pass")

    must_block(module, lambda f: f[1].__setitem__("head_sha", "b" * 40), "cross-RC run")
    must_block(module, lambda f: f[1].__setitem__("event", "pull_request"), "non-dispatch source")
    must_block(module, lambda f: f[1].__setitem__("conclusion", "failure"), "failed source run")
    must_block(module, lambda f: f[2]["jobs"][0].__setitem__("steps", None), "zero-execution required job")
    must_block(module, lambda f: f[2]["jobs"][2].__setitem__("conclusion", "skipped"), "skipped CodeQL")
    must_block(module, lambda f: f[2]["jobs"].pop(3), "missing CodeQL matrix member")
    must_block(module, lambda f: f[2]["jobs"][-1].__setitem__("conclusion", "failure"), "release-gate failure")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    for token in (
        "workflow_dispatch",
        "Security Release Gate",
        ".head_sha",
        "$RC_SHA",
        "actions/runs/${SECURITY_RUN_ID}/jobs?per_page=100",
        "security-release-decision.py",
        'prefix="${SECURITY_DIR}/"',
        'git push origin "HEAD:${GITHUB_REF_NAME}"',
    ):
        require(token in workflow, f"freezer workflow missing {token!r}")

    require(
        "workflow-run.json" in workflow and "jobs.json" in workflow,
        "freezer must persist raw run and job metadata",
    )
    require(
        'test "$(jq -r \'.event\'' in workflow and '"workflow_dispatch"' in workflow,
        "freezer must require workflow_dispatch source evidence",
    )
    require(
        'test "$(jq -r \'.head_sha\'' in workflow,
        "freezer must compare exact RC head_sha",
    )

    print("security release decision contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
