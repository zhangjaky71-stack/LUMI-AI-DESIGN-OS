from __future__ import annotations

import importlib.metadata
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "apps" / "agent-runtime" / "src" / "lumi_agent_runtime" / "deep_runtime"
PYPROJECT = ROOT / "apps" / "agent-runtime" / "pyproject.toml"
SANDBOX_ADAPTER = (
    ROOT
    / "services"
    / "sandbox-runtime"
    / "src"
    / "lumi_sandbox_runtime"
    / "deepagents_adapter.py"
)

REQUIRED = {
    "__init__.py",
    "contracts.py",
    "errors.py",
    "executor.py",
    "factory.py",
    "filesystem.py",
    "ports.py",
    "prompting.py",
    "providers.py",
    "structured_result.py",
    "testing.py",
    "tooling.py",
}
OBSOLETE = {
    "control_plane.py",
    "graph_limits.py",
    "node25_adapter.py",
    "registry.py",
    "runtime_factory.py",
}
PROVIDER_MARKERS = (
    "from openai",
    "import openai",
    "from anthropic",
    "import anthropic",
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
)
HOST_SHELL_MARKERS = ("subprocess.", "os.system(", "shell=true", "shell = true")


def main() -> None:
    current = {path.name for path in PKG.glob("*.py")}
    missing = REQUIRED - current
    assert not missing, f"missing NODE-29 runtime files: {sorted(missing)}"
    leaked = OBSOLETE & current
    assert not leaked, f"obsolete old-chain modules remain: {sorted(leaked)}"

    pyproject = PYPROJECT.read_text(encoding="utf-8")
    assert '"deepagents==0.6.12"' in pyproject
    assert '"langchain==1.3.14"' in pyproject
    assert '"langgraph==1.2.9"' in pyproject
    assert importlib.metadata.version("deepagents") == "0.6.12"

    from deepagents import create_deep_agent

    params = inspect.signature(create_deep_agent).parameters
    for name in (
        "model",
        "tools",
        "system_prompt",
        "subagents",
        "backend",
        "checkpointer",
        "skills",
        "response_format",
        "store",
    ):
        assert name in params, f"deepagents 0.6.12 factory contract missing {name}"

    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in PKG.glob("*.py")
    }
    combined = "\n".join(sources.values()).casefold()
    for marker in PROVIDER_MARKERS:
        assert marker not in combined, f"provider boundary bypass: {marker}"
    for marker in HOST_SHELL_MARKERS:
        assert marker not in combined, f"host shell boundary bypass: {marker}"

    factory = sources["factory.py"]
    assert "create_deep_agent" in factory
    assert 'kwargs["skills"] = ["/skills/"]' in factory
    assert 'kwargs["response_format"] = AGENT_TASK_RESULT_SCHEMA' in factory
    assert "_lumi_model_gateway_bound" in factory
    assert "_lumi_budget_meter_bound" in factory
    assert "assert_trusted_backend" in factory

    tooling = sources["tooling.py"]
    for marker in (
        "InjectedToolCallId",
        "_RESERVED_SCOPE_KEYS",
        "before_tool_call",
        "idempotency_key",
        "_lumi_tool_gateway_bound",
    ):
        assert marker in tooling

    filesystem = sources["filesystem.py"]
    assert "backend exposes execute without granted permission" in filesystem
    assert "_lumi_sandbox_execute_bound" in filesystem
    assert "/workspace/input" in filesystem
    assert "/workspace/work" in filesystem
    assert "/workspace/output" in filesystem
    assert "/skills" in filesystem
    assert "/memory" in filesystem

    prompting = sources["prompting.py"]
    assert "pinned_project_constraints" in prompting
    assert 'immutable=\\"true\\"' in repr(prompting)
    assert "treat_as_data" in prompting
    assert "do not expose private reasoning" in prompting.casefold()

    executor = sources["executor.py"]
    assert "proposed_operations" not in executor.split("_safe_control_delta", 1)[1]
    assert "agent-result://" not in executor
    assert "factory.compile" in executor

    result = sources["structured_result.py"]
    for field in (
        "status",
        "summary",
        "decisions",
        "artifact_refs",
        "knowledge_refs",
        "proposed_operations",
        "open_questions",
        "confidence",
    ):
        assert f'"{field}"' in result
    assert "remained invalid after one repair" in result

    sandbox = SANDBOX_ADAPTER.read_text(encoding="utf-8")
    assert "class DeepAgentsSandboxAdapter(SandboxBackendProtocol)" in sandbox
    assert "SandboxRuntimeService" in sandbox
    assert "DockerSandboxBackend" in sandbox
    assert "shell operators are not allowed" in sandbox

    main_graph = (
        ROOT
        / "apps"
        / "agent-runtime"
        / "src"
        / "lumi_agent_runtime"
        / "control_plane"
        / "main_graph.py"
    ).read_text(encoding="utf-8")
    assert "services.agentic.execute(state)" in main_graph

    print(
        "NODE-29 Deep Agents Runtime validation PASS: pinned deepagents contract, "
        "Model/Tool/Sandbox boundaries, scope injection defense, native skills, "
        "structured output, and NODE-28 agentic-node seam are present"
    )


if __name__ == "__main__":
    main()
