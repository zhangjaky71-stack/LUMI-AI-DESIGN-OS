from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-29 marker: {needle}")
    return text


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-29 marker: {needle}")


def assert_no_ambient_authority() -> None:
    root = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime"
    forbidden_imports = {
        "asyncpg",
        "boto3",
        "docker",
        "openai",
        "anthropic",
        "psycopg",
        "requests",
        "sqlalchemy",
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
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/contracts.py",
        "class DeepAgentDefinition",
        "class DeepSubagentDefinition",
        "class DeepAgentInvocationContext",
        "class SubagentInvocationContext",
        "class DelegationLimits",
        "DEEP_AGENT_SUBAGENT_TOOL_ESCALATION",
        "DEEP_SUBAGENT_CONTEXT_TOOL_ESCALATION",
        "content_hash",
        "max_total_subagent_calls",
        "max_parallel_subagents",
    )
    factory = require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/factory.py",
        "create_deep_agent",
        "current deepagents package with create_deep_agent is required",
        'required = {"model", "tools", "system_prompt", "subagents", "backend", "checkpointer"}',
        "NODE-29 P0 forbids nested subagent delegation",
        "_lumi_model_gateway_bound",
        "_lumi_tool_gateway_bound",
        "_lumi_backend_bound",
        "host-local Deep Agents backend is forbidden",
        "deep_agent_definition_hash",
        "recursion_limit",
    )
    forbid(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/factory.py",
        "FilesystemBackend(",
        "LocalShellBackend(",
        "DockerBackend(",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/graph_limits.py",
        "class LimitedCompiledDeepAgent",
        "min(requested_recursion, self._recursion_limit)",
        "min(requested_concurrency, self._max_concurrency)",
    )
    tooling = require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/tooling.py",
        "InjectedToolCallId",
        "StructuredTool",
        "deep-agent:{context.agent_run_id}:{tool_call_id}",
        "NODE-25 Tool Gateway",
        "tool_call_id",
    )
    if "uuid4()" in tooling:
        raise SystemExit("Deep Agent write-tool idempotency must not use a random call identity")
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/node25_adapter.py",
        "class Node25ToolGatewayInvoker",
        "ToolPermissionContext",
        "ToolRequest",
        "parent_allow_patterns",
        "agent_allow_patterns",
        "idempotency_key",
        "NODE-25 Tool Gateway contracts are unavailable",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/ports.py",
        "class DeepAgentModelProvider",
        "NODE-22 Model Gateway",
        "class DeepAgentToolProvider",
        "NODE-25",
        "class DeepAgentBackendProvider",
        "class DeepAgentCheckpointerProvider",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/control_plane.py",
        "class DeepAgentControlPlaneCompiler",
        "deep_agent_definition_hash",
        "DurableCompiledGraphRegistry",
        "GraphRegistry",
        "graph_catalog.verify",
    )
    public = require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/__init__.py",
        "BoundedDeepAgentRuntimeFactory",
        "LumiToolGatewayProvider",
        "Node25ToolGatewayInvoker",
        "DeepAgentControlPlaneCompiler",
    )
    if "DeepAgentRuntimeFactory" in public:
        raise SystemExit("unbounded raw DeepAgentRuntimeFactory must not be public API")
    require(
        "scripts/integration_deep_agents_runtime.py",
        "FinalAnswerModel",
        "StateBackend",
        "create_deep_agent",
        "NODE29_DEEP_AGENT_OK",
        "max_concurrency",
    )
    require(
        "scripts/integration_deep_agent_tool_gateway.py",
        'assert "tool_call_id" not in properties',
        "deep-agent:{context.agent_run_id}:{call_id}",
        '"type": "tool_call"',
    )
    require(
        "apps/agent-runtime/tests/test_deep_runtime_factory.py",
        "test_unmarked_model_is_rejected",
        "test_tool_provider_cannot_expand_scope",
        "test_nested_subagent_delegation_is_fail_closed_in_p0",
        "test_compiled_graph_limits_cannot_be_widened_by_caller",
    )
    require(
        "apps/agent-runtime/tests/test_deep_runtime_contracts.py",
        "test_child_tool_scope_must_be_subset_of_root",
        "test_definition_hash_changes_when_child_scope_changes",
    )
    require(
        "apps/agent-runtime/tests/test_deep_runtime_tooling.py",
        "test_framework_tool_call_id_becomes_stable_idempotency_key",
        "test_subagent_parent_scope_is_forwarded",
    )
    assert_no_ambient_authority()
    print("NODE-29 Deep Agents runtime static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
