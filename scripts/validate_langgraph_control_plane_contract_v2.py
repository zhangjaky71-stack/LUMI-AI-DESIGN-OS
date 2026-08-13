from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-28 marker: {needle}")
    return text


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-28 marker: {needle}")


def assert_no_ambient_authority() -> None:
    root = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/control_plane"
    forbidden_imports = {
        "boto3",
        "docker",
        "openai",
        "anthropic",
        "requests",
        "subprocess",
    }
    forbidden_markers = {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "/var/run/docker.sock",
    }
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for marker in forbidden_markers:
            if marker in text:
                raise SystemExit(f"{path}: ambient authority marker: {marker}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                if roots & forbidden_imports:
                    raise SystemExit(f"{path}: forbidden import: {roots & forbidden_imports}")
            if isinstance(node, ast.ImportFrom) and node.module:
                root_name = node.module.split(".", 1)[0]
                if root_name in forbidden_imports:
                    raise SystemExit(f"{path}: forbidden import: {root_name}")


def main() -> int:
    migration = require(
        "apps/api/alembic/versions/0012_langgraph_control_plane.py",
        'down_revision = "0011_cost_ledger_budget_quota"',
        "CREATE TABLE agent_graph_definitions",
        "CREATE TABLE agent_run_control",
        "uq_agent_graph_definitions_identity",
        "uq_agent_run_control_thread",
        "graph_definition_hash",
        "checkpoint_id",
        "checkpoint_namespace",
        "interrupts_json",
        "REVOKE INSERT, UPDATE, DELETE ON agent_graph_definitions FROM lumi_app",
        "REVOKE DELETE ON agent_run_control FROM lumi_app",
        "GRANT SELECT ON agent_graph_definitions TO lumi_app",
        "GRANT SELECT, INSERT, UPDATE ON agent_run_control TO lumi_app",
    )
    if "GRANT SELECT, INSERT, UPDATE ON agent_graph_definitions" in migration:
        raise SystemExit("runtime must not mutate graph definitions")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/contracts.py",
        "class GraphDefinition",
        "class GraphRunRequest",
        "class GraphRunSnapshot",
        "class GraphInterrupt",
        "class ResumeRequest",
        "class ResumeAuthorization",
        "graph_version",
        "agent_config_version",
        "thread_id",
        "checkpoint_id",
        "GRAPH_BINARY_VALUE_FORBIDDEN",
        "GRAPH_NON_FINITE_NUMBER",
    )
    control = require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/control_plane.py",
        "class LangGraphControlPlane",
        'operation_type="langgraph.start"',
        'operation_type="langgraph.resume"',
        'operation_type="langgraph.cancel"',
        "fresh = await self.store.load",
        "authorization = await self.resume_authorizer.authorize",
        "authorization.bound_interrupt_id",
        "normalized_value=authorization.normalized_value",
        "expected_checkpoint=expected",
    )
    if "normalized_value=request.value" in control:
        raise SystemExit("client resume value bypasses LUMI authorization")

    durable = require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/durable_executor.py",
        "class ThreadGraphBinding",
        "class DurableCompiledGraphRegistry",
        "class DurableLangGraphExecutor",
        "compiled graph has no checkpointer",
        "binding = await self.bindings.resolve_thread",
        "command_type(resume=normalized_value)",
        '"configurable": {"thread_id": thread_id}',
        "LangGraph checkpoint read failed",
    )
    if "for key, definition in self.definitions.items()" in durable:
        raise SystemExit("durable executor must not scan graphs to infer thread binding")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/checkpointing.py",
        "langgraph.checkpoint.postgres.aio",
        "AsyncPostgresSaver",
        "allow_setup",
        "await saver.setup()",
        "already initialized checkpoint schema",
    )
    store = require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/postgres_store.py",
        "class PostgresGraphRunStore",
        "langgraph-run:",
        "pg_advisory_xact_lock",
        "checkpoint advanced before control-plane persist",
        "graph_definition_hash",
        "resolve_thread",
    )
    if "import asyncpg" in store or "from asyncpg" in store:
        raise SystemExit("Agent Runtime Postgres store must remain DB-SDK-neutral")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/postgres_catalog.py",
        "class PostgresGraphDefinitionCatalog",
        "immutable graph version already exists with different content",
        "runtime graph definition differs from durable catalog",
        "enabled=$3",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/resume_policy.py",
        "class PolicyResumeAuthorizer",
        "approval does not belong to AgentRun scope",
        "resume decision does not match durable approval decision",
        "approval is still pending",
        "input resume validator is not installed",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/interrupts.py",
        "langgraph.types",
        "Approval service",
        "interrupt(payload)",
    )
    public = require(
        "apps/agent-runtime/src/lumi_agent_runtime/control_plane/__init__.py",
        "DurableLangGraphExecutor",
        "PostgresGraphRunStore",
        "PolicyResumeAuthorizer",
    )
    if "from .langgraph_adapter import" in public or '"LangGraphExecutor"' in public:
        raise SystemExit("thread-scanning exploratory executor must not be public")

    require(
        "scripts/integration_langgraph_control_plane.py",
        "InMemorySaver",
        "StateGraph",
        "interrupt(",
        'counts == {"draft": 1, "review": 2, "finish": 1}',
    )
    require(
        "scripts/integration_langgraph_postgres_checkpoint.py",
        "open_postgres_checkpointer",
        "allow_setup=True",
        "allow_setup=False",
        "Simulate runtime restart",
        "restarted.resume",
    )
    require(
        "scripts/integration_langgraph_postgres_control.py",
        "stale checkpoint persist must fail",
        "runtime mutation must be denied",
    )
    require(
        "apps/agent-runtime/tests/test_control_plane.py",
        "test_duplicate_start_operation_executes_graph_once",
        "test_resume_uses_authorized_normalized_value_not_client_value",
        "test_wrong_interrupt_id_never_calls_authorizer_or_executor",
        "test_store_checkpoint_compare_and_swap_rejects_stale_persist",
    )
    require(
        "apps/agent-runtime/tests/test_resume_policy.py",
        "test_durable_rejection_is_authorized_resume_with_rejected_value",
        "test_pending_approval_does_not_resume",
        "test_tenant_mismatch_is_denied",
    )
    assert_no_ambient_authority()
    print("NODE-28 LangGraph control-plane static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
