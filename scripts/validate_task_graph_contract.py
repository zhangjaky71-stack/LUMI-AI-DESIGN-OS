from __future__ import annotations

import ast
from pathlib import Path

from lumi_agent_runtime.task_graph import TaskState, logical_operation_key

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/task_graph"
EXPECTED_STATES = {
    "PENDING",
    "READY",
    "RUNNING",
    "WAITING_APPROVAL",
    "WAITING_INPUT",
    "WAITING_EXTERNAL",
    "SUCCEEDED",
    "FAILED_RETRYABLE",
    "FAILED_FINAL",
    "CANCELLED",
    "SKIPPED",
}
FORBIDDEN_IMPORTS = {
    "asyncpg",
    "sqlalchemy",
    "psycopg",
    "requests",
    "subprocess",
    "docker",
    "openai",
    "anthropic",
    "google",
}


def require(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"{path}: missing NODE-33 marker: {marker}")
    return text


def main() -> int:
    if {item.value for item in TaskState} != EXPECTED_STATES:
        raise SystemExit("NODE-33 TaskState contract drifted")

    fake_graph = __import__("uuid").uuid4()
    fake_task = __import__("uuid").uuid4()
    logical = logical_operation_key(fake_graph, fake_task)
    if logical != f"task:{fake_graph}:{fake_task}" or "attempt" in logical:
        raise SystemExit("NODE-33 logical operation key must be stable across retries")

    migration = require(
        "apps/api/alembic/versions/0015_task_graph_runtime.py",
        'down_revision = "0014_agent_registry_provenance"',
        '"task_graph_instances"',
        '"task_attempts"',
        'op.add_column("tasks"',
        'sa.Column("task_graph_id"',
        'sa.Column("owner_key"',
        'sa.Column("budget_limit_usd"',
        'sa.Column("output_schema"',
        'sa.Column("metadata_json"',
        'sa.Column("cancellation_requested_at"',
        'sa.Column("logical_operation_key"',
        'sa.UniqueConstraint("task_id", "attempt_number"',
        '"ix_tasks_ready_claim"',
        '"ix_tasks_lease_reap"',
        '"ix_tasks_concurrency_group"',
        'REVOKE DELETE ON task_attempts FROM lumi_app',
        'GRANT SELECT, INSERT, UPDATE ON task_attempts TO lumi_app',
    )
    if 'op.create_table(\n        "tasks"' in migration:
        raise SystemExit("NODE-33 must reuse existing tasks ledger")
    if 'sa.UniqueConstraint("logical_operation_key"' in migration:
        raise SystemExit("logical operation key must be reusable across attempts")

    store = require(
        "apps/agent-runtime/src/lumi_agent_runtime/task_graph/postgres_store.py",
        "FOR UPDATE SKIP LOCKED",
        "LIMIT 1",
        "state_version = state_version + 1",
        "AND state_version = $6",
        "INSERT INTO task_attempts",
        "logical_operation_key",
        "INSERT INTO outbox_events",
        "event_name, aggregate_type",
        "aggregate_id, schema_version, payload_json, publish_attempts",
        "INSERT INTO tasks (",
        "task_key, type, status, owner_agent_key, owner_key",
        "input_json, output_json",
        "budget_reserved, budget_limit_usd",
        "output_schema, metadata_json",
        "INSERT INTO task_dependencies",
        "id, organization_id, task_id, depends_on_task_id",
        "TASK_ATTEMPT_FINISH_CONFLICT",
        "TASK_ATTEMPT_RECLAIM_CONFLICT",
        "provider_reconciliation_required",
        "async def load_graph",
        "async def list_tasks",
        "async def list_attempts",
        "async def timeline",
        "async def heartbeat",
        "async def finish_running",
        "async def resume_waiting",
        "async def schedule_retry",
        "async def reclaim_expired",
        "async def request_cancel",
    )
    for forbidden in ("task_key, kind", "owner_agent,", "event_type"):
        if forbidden in store:
            raise SystemExit(f"NODE-33 store uses non-canonical schema marker: {forbidden}")
    if store.count("AND status = 'RUNNING'") < 4:
        raise SystemExit("NODE-33 attempt/lease lifecycle must be RUNNING guarded")

    workflow = require(
        "apps/api/src/lumi_api/persistence/models/workflow.py",
        "task_graph_id:",
        "owner_key:",
        "budget_limit_usd:",
        "output_schema:",
        "metadata_json:",
        "cancellation_requested_at:",
        "lease_expires_at:",
        "concurrency_limit:",
    )
    if "class Task(" not in workflow:
        raise SystemExit("NODE-33 Task ORM missing")
    require(
        "apps/api/src/lumi_api/persistence/models/task_graph.py",
        "class TaskGraphInstance",
        "class TaskAttemptRecord",
        '"task_graph_instances"',
        '"task_attempts"',
    )
    require(
        "apps/api/src/lumi_api/persistence/models/__init__.py",
        "from .task_graph import TaskAttemptRecord, TaskGraphInstance",
        '"TaskAttemptRecord"',
        '"TaskGraphInstance"',
    )

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/task_graph/claims.py",
        "provider_reconciliation_required",
        "logical_operation_key",
        "lease_expires_at",
        "heartbeat_at",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/task_graph/lifecycle.py",
        'policy == "ANY"',
        'policy == "MIN_SUCCESS"',
        "evaluate_expression",
        "CONDITION_FALSE",
        "UPSTREAM_JOIN_UNSATISFIED",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/task_graph/cancellation.py",
        "cancellation_requested_at",
        "TASK_CANCEL_ACK_INVALID",
        "TaskState.RUNNING",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/task_graph/dynamic.py",
        "parent.dynamic_depth >= 4",
        "TASK_DYNAMIC_CHILD_LIMIT",
        "TASK_DYNAMIC_BUDGET_ESCALATION",
        "TASK_DYNAMIC_CONCURRENCY_ESCALATION",
        "TASK_DYNAMIC_CHILD_SCOPE_ESCALATION",
        "task_count=graph.task_count + 1",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/compiler.py",
        '"node33_contract": "TaskGraphTemplate:v1"',
    )

    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                bad = roots & FORBIDDEN_IMPORTS
                if bad:
                    raise SystemExit(
                        f"Task Graph imports ambient authority: {path}:{sorted(bad)}"
                    )
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in FORBIDDEN_IMPORTS:
                    raise SystemExit(
                        f"Task Graph imports ambient authority: {path}:{root}"
                    )

    print("NODE-33 Task Graph static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
