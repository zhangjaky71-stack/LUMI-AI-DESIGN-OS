from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/control_plane"
MIGRATION = ROOT / "apps/api/migrations/versions/20260816_0010_langgraph_control_plane.py"
UP = ROOT / "apps/api/migrations/versions/20260816_0010_sql/up_01.sql"
UP_SECURITY = ROOT / "apps/api/migrations/versions/20260816_0010_sql/up_02.sql"
DOWN_GUARD = ROOT / "apps/api/migrations/versions/20260816_0010_sql/down_02.sql"
GAPS = ROOT / "reports/nodes/NODE-28/gap-ledger.json"

REQUIRED = {
    "contracts.py",
    "errors.py",
    "events.py",
    "ports.py",
    "main_graph.py",
    "runtime.py",
    "checkpointing.py",
    "postgres_store.py",
    "testing.py",
    "__init__.py",
}
FORBIDDEN_IMPORTS = {
    "openai",
    "anthropic",
    "google.generativeai",
    "requests",
    "httpx",
    "urllib.request",
}


def main() -> int:
    missing = [name for name in REQUIRED if not (CONTROL / name).exists()]
    assert not missing, f"missing NODE-28 files: {missing}"

    main_graph = (CONTROL / "main_graph.py").read_text(encoding="utf-8")
    runtime = (CONTROL / "runtime.py").read_text(encoding="utf-8")
    checkpointing = (CONTROL / "checkpointing.py").read_text(encoding="utf-8")
    contracts = (CONTROL / "contracts.py").read_text(encoding="utf-8")
    ports = (CONTROL / "ports.py").read_text(encoding="utf-8")
    store = (CONTROL / "postgres_store.py").read_text(encoding="utf-8")

    assert 'GRAPH_KEY = "lumi.main"' in main_graph
    assert 'GRAPH_VERSION = "1.0.0"' in main_graph
    for category in (
        "DETERMINISTIC",
        "AGENTIC",
        "SIDE_EFFECT",
        "WAIT_EXTERNAL",
        "HUMAN_INTERRUPT",
    ):
        assert f"NodeCategory.{category}" in main_graph
    for node in (
        "validate_run",
        "load_project_snapshot",
        "select_or_load_recipe",
        "ensure_task_graph",
        "route_ready_tasks",
        "deterministic_task",
        "deep_agent_task",
        "side_effect_task",
        "media_job_wait",
        "approval_interrupt",
        "collect_results",
        "quality_gate",
        "finalize",
    ):
        assert f'"{node}"' in main_graph

    assert "interrupt(" in main_graph
    assert "Command(resume=normalized_value)" in runtime
    assert "execute_idempotent" in ports and "execute_idempotent" in main_graph
    assert "submit_idempotent" in ports and "submit_idempotent" in main_graph
    assert "LANGGRAPH_STRICT_MSGPACK" in checkpointing
    assert "InMemorySaver" in checkpointing
    assert "set_config('app.current_organization_id'" in store
    assert "expected_resume_version" in store and "expected_checkpoint_id" in store
    assert "GRAPH_STATE_UNKNOWN_KEYS" in contracts
    assert "GRAPH_STATE_INLINE_DATA_URI_FORBIDDEN" in contracts
    assert "GRAPH_EVENT_PRIVATE_REASONING_FORBIDDEN" in contracts

    for path in CONTROL.glob("*.py"):
        _assert_no_forbidden_imports(path)

    migration = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260816_0010"' in migration
    assert 'down_revision = "20260816_0009"' in migration
    up = UP.read_text(encoding="utf-8")
    security = UP_SECURITY.read_text(encoding="utf-8")
    guard = DOWN_GUARD.read_text(encoding="utf-8")
    for marker in (
        "agent_graph_definitions",
        "agent_run_control",
        "resume_version",
        "graph_key",
        "graph_version",
        "code_git_sha",
        "waiting_external",
        "cancel_requested",
    ):
        assert marker in up
    assert "ENABLE ROW LEVEL SECURITY" in security
    assert "tenant_isolation_agent_run_control" in security
    assert "durable AgentRun control state exists" in guard

    ledger = json.loads(GAPS.read_text(encoding="utf-8"))
    assert len(ledger["gaps"]) == 8
    gap_ids = {item["id"] for item in ledger["gaps"]}
    assert "GRAPH-CHECKPOINT-PACKAGE-001" in gap_ids
    assert "GRAPH-STORE-PACKAGE-002" in gap_ids
    assert "GRAPH-CI-008" in gap_ids

    agent_project = (
        ROOT / "apps/agent-runtime/pyproject.toml"
    ).read_text(encoding="utf-8")
    assert "langgraph==1.2.9" in agent_project
    assert "langgraph-checkpoint-postgres" not in agent_project
    assert "asyncpg" not in agent_project

    print("NODE-28 LangGraph control-plane static validation: PASS")
    return 0


def _assert_no_forbidden_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert not any(
                name == blocked or name.startswith(blocked + ".")
                for blocked in FORBIDDEN_IMPORTS
            ), f"forbidden direct dependency {name} in {path}"


if __name__ == "__main__":
    raise SystemExit(main())
