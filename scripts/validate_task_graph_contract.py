from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

from lumi_agent_runtime.task_graph import (
    DurableTaskGraphScheduler,
    TaskState,
    logical_operation_key,
)

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
REQUIRED_MODULES = {
    "errors.py",
    "events.py",
    "task_contracts.py",
    "instantiator.py",
    "lifecycle.py",
    "complete_fail.py",
    "claims.py",
    "cancellation.py",
    "dynamic.py",
    "memory_store.py",
    "postgres_store.py",
    "scheduler.py",
    "state_machine.py",
    "states.py",
    "wait_progress.py",
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
    missing = sorted(name for name in REQUIRED_MODULES if not (PACKAGE / name).is_file())
    if missing:
        raise SystemExit(f"NODE-33 runtime modules missing: {missing}")
    if {item.value for item in TaskState} != EXPECTED_STATES:
        raise SystemExit("NODE-33 TaskState contract drifted")
    if not isinstance(DurableTaskGraphScheduler, type):
        raise SystemExit("NODE-33 durable scheduler is not public")

    graph_id, task_id = uuid4(), uuid4()
    logical = logical_operation_key(graph_id, task_id)
    if logical != f"task:{graph_id}:{task_id}" or "attempt" in logical:
        raise SystemExit("NODE-33 logical operation key must be stable across retries")

    migration = require(
        "apps/api/alembic/versions/0015_task_graph_runtime.py",
        'down_revision = "0014_agent_registry_provenance"',
        '"task_graph_instances"',
        '"task_attempts"',
        'op.add_column("tasks"',
        'sa.Column("task_graph_id"',
        'sa.Column("condition_expression"',
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
        "AND state_version = $6",
        "g.status = 'RUNNING'",
        "INSERT INTO task_attempts",
        "logical_operation_key",
        "INSERT INTO outbox_events",
        "event_name, aggregate_type",
        "id, organization_id, task_id, depends_on_task_id",
        "owner_agent_key, owner_key",
        "output_schema, condition_expression, metadata_json",
        "task.condition",
        "TASK_ATTEMPT_FINISH_CONFLICT",
        "TASK_ATTEMPT_RECLAIM_CONFLICT",
        "provider_reconciliation_required",
        "async def add_dynamic_task",
        "TASK_DYNAMIC_BUDGET_ESCALATION",
        "TASK_DYNAMIC_CONCURRENCY_ESCALATION",
        "async def _set_graph_running",
        'status = "WAITING"',
    )
    for forbidden in (
        "task_key, kind",
        "owner_agent,",
        "event_type",
        "g.status IN ('PENDING','RUNNING')",
        'status = "PENDING"',
    ):
        if forbidden in store:
            raise SystemExit(f"NODE-33 store uses invalid schema/state marker: {forbidden}")

    require(
        "apps/api/src/lumi_api/persistence/models/workflow.py",
        "task_graph_id:",
        "owner_key:",
        "condition_expression:",
        "cancellation_requested_at:",
        "lease_expires_at:",
        "concurrency_limit:",
    )
    require(
        "apps/api/src/lumi_api/persistence/models/task_graph.py",
        "class TaskGraphInstance",
        "class TaskAttemptRecord",
    )
    require(
        "apps/api/src/lumi_api/persistence/models/__init__.py",
        "from .task_graph import TaskAttemptRecord, TaskGraphInstance",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/task_graph/claims.py",
        "provider_reconciliation_required",
        "logical_operation_key",
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
        "apps/agent-runtime/src/lumi_agent_runtime/task_graph/scheduler.py",
        "class DurableTaskGraphScheduler",
        "_join_decision",
        "_condition_context",
        "await self.store.mark_ready",
        "await self.store.claim_ready",
        "await self.store.reclaim_expired",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/task_graph/dynamic.py",
        "parent.dynamic_depth >= 4",
        "TASK_DYNAMIC_CHILD_LIMIT",
        "TASK_DYNAMIC_BUDGET_ESCALATION",
        "TASK_DYNAMIC_CONCURRENCY_ESCALATION",
        "TASK_DYNAMIC_CHILD_SCOPE_ESCALATION",
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
                if roots & FORBIDDEN_IMPORTS:
                    raise SystemExit(f"Task Graph imports ambient authority: {path}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".", 1)[0] in FORBIDDEN_IMPORTS:
                    raise SystemExit(f"Task Graph imports ambient authority: {path}")

    print("NODE-33 Task Graph static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
