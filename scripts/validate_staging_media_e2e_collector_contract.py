#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "apps/api/src/lumi_api/staging_media_e2e_collector.py"
CONTRACT = ROOT / "staging/acceptance/media-generation-e2e-v1.json"
COLLECT_WORKFLOW = ROOT / ".github/workflows/collect-staging-media-generation-e2e.yml"
FREEZE_WORKFLOW = ROOT / ".github/workflows/freeze-staging-media-generation-e2e.yml"
VALIDATOR = ROOT / "scripts/validate_media_generation_e2e_evidence.py"


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _source(path: Path) -> str:
    require(path.is_file(), f"required source is missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _json(path: Path) -> dict[str, Any]:
    raw = json.loads(_source(path))
    require(isinstance(raw, dict), f"{path.relative_to(ROOT)} must be a JSON object")
    return raw


def validate_collector() -> None:
    source = _source(COLLECTOR)
    tree = ast.parse(source, filename=str(COLLECTOR))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    forbidden_provider_roots = {"openai", "anthropic", "google", "replicate"}
    require(
        not (imported_roots & forbidden_provider_roots),
        "staging media E2E collector must never import Provider SDKs directly",
    )
    required_fragments = [
        'environment != "staging"',
        'f"http://api.{environment}.lumi.internal:{_API_PORT}"',
        'scopes=frozenset({"project.read", "project.write"})',
        "AuthService(session).create_api_token",
        "PrincipalResolver(session).revoke_api_token",
        'evidence_key.startswith("acceptance/node73/e2e-03/")',
        '"synthetic_only": True',
        '"status": "PASS"',
        'generation.status != "completed"',
        'task.status != "succeeded"',
        "JobDispatch.from_outbox_payload",
        'code_git_sha != release_sha',
    ]
    for fragment in required_fragments:
        require(fragment in source, f"collector contract missing boundary: {fragment}")
    forbidden_fragments = [
        "LUMI_MODEL_PROVIDER_SECRET",
        "LUMI_MEDIA_PROVIDER_SECRET",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        'scopes=frozenset({"*"})',
    ]
    for fragment in forbidden_fragments:
        require(fragment not in source, f"collector contains forbidden Provider/privilege boundary: {fragment}")


def validate_evidence_contract() -> None:
    contract = _json(CONTRACT)
    require(contract.get("scenario_id") == "E2E-03", "media E2E contract must bind E2E-03")
    require(
        contract.get("required_terminal_state")
        == {"task_status": "succeeded", "generation_status": "completed"},
        "media E2E terminal state must match canonical Task/Generation persistence semantics",
    )
    require(
        contract.get("required_evidence_stages")
        == [
            "api_request",
            "generation_row",
            "task_row",
            "outbox_dispatch",
            "worker_execution",
            "artifact",
            "provenance",
        ],
        "media E2E evidence stages drifted",
    )
    validator = _source(VALIDATOR)
    for fragment in [
        "canonical_snapshot_sha256(snapshot)",
        "validate_snapshot_safety(snapshot",
        '"authorization"',
        '"api_token"',
        '"secret"',
        '"generation_status": "completed"',
    ]:
        require(fragment in validator, f"media E2E validator missing fail-closed boundary: {fragment}")


def validate_workflows() -> None:
    collect = _source(COLLECT_WORKFLOW)
    freeze = _source(FREEZE_WORKFLOW)

    require("workflow_dispatch:" in collect, "collector workflow must be explicitly dispatched")
    require("pull_request:" not in collect and "push:" not in collect, "collector workflow must not auto-run on push/PR")
    for fragment in [
        "COLLECT_STAGING_E2E",
        "id-token: write",
        "EXPECTED_API_IMAGE: ${{ vars.API_IMAGE_DIGEST }}",
        "aws ecs describe-task-definition",
        'test "$deployed_image" = "$EXPECTED_API_IMAGE"',
        'command: ["python", "-m", "lumi_api.staging_media_e2e_collector"]',
        "media-e2e-runtime-identity.json",
        "validate_media_generation_e2e_evidence.py --self-test",
    ]:
        require(fragment in collect, f"collector workflow missing release boundary: {fragment}")

    require("workflow_dispatch:" in freeze, "freeze workflow must be explicitly dispatched")
    require("pull_request:" not in freeze and "push:" not in freeze, "freeze workflow must not auto-run on push/PR")
    for fragment in [
        "contents: write",
        "actions: read",
        "FREEZE_STAGING_MEDIA_E2E:${RC_SHA}",
        'test "$(jq -r \'.name\' <<<"$run")" = "Collect Staging Media Generation E2E"',
        'test "$(jq -r \'.head_sha\' <<<"$run")" = "$RC_SHA"',
        "media-generation-e2e.json",
        "media-e2e-runtime-identity.json",
        'destination="reports/staging-acceptance/${RC_SHA}/media-generation-e2e"',
        "refusing to overwrite non-identical frozen staging media E2E evidence",
        "validate_media_generation_e2e_evidence.py --self-test",
    ]:
        require(fragment in freeze, f"freeze workflow missing immutable evidence boundary: {fragment}")


def main() -> int:
    try:
        validate_collector()
        validate_evidence_contract()
        validate_workflows()
    except (ContractError, OSError, SyntaxError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "contract": "staging-media-generation-e2e",
                "scenario_id": "E2E-03",
                "collector_transport": "deployed-api-http",
                "evidence_freeze": "immutable-rc-path",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
