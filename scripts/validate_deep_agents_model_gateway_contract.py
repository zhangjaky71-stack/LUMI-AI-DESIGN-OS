from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing Deep Agent/Model Gateway marker: {needle}")
    return text


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden Deep Agent/Model Gateway marker: {needle}")


def assert_model_chat_boundary() -> None:
    path = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/model_gateway_chat.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    forbidden_modules = {
        "openai",
        "anthropic",
        "cohere",
        "mistralai",
        "groq",
        "replicate",
        "fal_client",
        "together",
        "requests",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
            if roots & forbidden_modules:
                raise SystemExit(f"{path}: provider/direct HTTP import bypasses NODE-22")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in forbidden_modules:
                raise SystemExit(f"{path}: provider/direct HTTP import bypasses NODE-22")
    for credential in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "COHERE_API_KEY",
        "MISTRAL_API_KEY",
        "GROQ_API_KEY",
        "REPLICATE_API_TOKEN",
        "FAL_KEY",
        "TOGETHER_API_KEY",
    ):
        if credential in text:
            raise SystemExit(f"{path}: raw provider credential escapes Model Gateway: {credential}")


def assert_hosted_runtime_composition() -> None:
    path = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/runtime_factory.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hosted = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "HostedDeepAgentRuntimeFactory"
        ),
        None,
    )
    if hosted is None:
        raise SystemExit(f"{path}: HostedDeepAgentRuntimeFactory is missing")
    initializer = next(
        (
            node
            for node in hosted.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        ),
        None,
    )
    if initializer is None:
        raise SystemExit(f"{path}: hosted runtime constructor is missing")
    argument_names = {
        argument.arg
        for argument in (
            *initializer.args.posonlyargs,
            *initializer.args.args,
            *initializer.args.kwonlyargs,
        )
    }
    if "models" in argument_names:
        raise SystemExit(
            f"{path}: hosted runtime must not expose model-provider injection"
        )
    has_http_provider = False
    for node in ast.walk(initializer):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if (
            node.func.attr == "from_env"
            and isinstance(owner, ast.Name)
            and owner.id == "HttpProfileModelProvider"
        ):
            has_http_provider = True
            break
    if not has_http_provider:
        raise SystemExit(
            f"{path}: hosted runtime must construct HttpProfileModelProvider.from_env()"
        )


def main() -> int:
    require(
        "apps/agent-runtime/pyproject.toml",
        '"lumi-model-gateway"',
        '"deepagents==0.6.12"',
        '"langchain==1.3.14"',
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/model_gateway_chat.py",
        "class ModelGatewayChatModel(BaseChatModel)",
        "class HttpProfileModelProvider(ProfileModelProvider)",
        "HttpModelGatewayClient",
        '_lumi_model_gateway_bound: ClassVar[bool] = True',
        'constraints: dict[str, Any] = {"model_profile": self.model_profile}',
        'uuid5(parent_operation_id, f"lumi-model-turn-v1:{digest}")',
        'LUMI_MODEL_GATEWAY_URL',
        'LUMI_MODEL_GATEWAY_AUTH_SECRET',
        'caller_service=_DEFAULT_CALLER_SERVICE',
        "convert_to_openai_tool",
        '"role": "tool"',
        'output.kind == "tool_call"',
        "Field(repr=False, exclude=True)",
    )
    assert_model_chat_boundary()
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/contracts.py",
        "class SubagentInvocationContext",
        "budget_limit_usd: str | None = None",
        "_validate_budget_limit(self.budget_limit_usd)",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/factory.py",
        "budget_limit_usd=context.budget_limit_usd",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/runtime_factory.py",
        "class HostedDeepAgentRuntimeFactory(BoundedDeepAgentRuntimeFactory)",
        "models=HttpProfileModelProvider.from_env()",
    )
    assert_hosted_runtime_composition()
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/__init__.py",
        "HostedDeepAgentRuntimeFactory",
        "HttpProfileModelProvider",
        "ModelGatewayChatModel",
    )
    require(
        "apps/agent-runtime/tests/test_deep_runtime_model_gateway_chat.py",
        "test_same_turn_reuses_operation_id_and_changed_turn_gets_new_id",
        "test_tools_and_tool_results_stay_provider_neutral",
        "test_secret_is_not_serialized_or_repr_exposed",
        "test_profile_provider_propagates_root_and_subagent_budget",
        "test_missing_internal_gateway_config_fails_closed",
        "test_hosted_factory_does_not_expose_model_injection",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/profile_routing.py",
        "class ModelProfileRouter(ModelRouter)",
        "MODEL_PROFILE_MISMATCH",
        "MODEL_PROFILE_MATCH",
        "unknown model profile",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/openai_tool_adapter.py",
        "class OpenAIResponsesToolAdapter(OpenAIResponsesAdapter)",
        '"function_call_output"',
        '"function_call"',
        'ModelOutput(kind="tool_call"',
        "delivery_state=DeliveryState.ACCEPTED",
    )
    require(
        "apps/api/src/lumi_api/model_gateway_bootstrap.py",
        "OpenAIResponsesToolAdapter",
        "ModelProfileRouter",
        '"profiles"',
        "profile_routes",
    )
    require(
        "services/model-gateway/tests/test_model_profile_routing.py",
        "test_profile_is_a_hard_provider_model_constraint",
        "test_unknown_profile_fails_closed",
    )
    forbid(
        "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/model_gateway_chat.py",
        "urllib.request",
        "httpx",
        "aiohttp",
    )
    print("NODE-22/NODE-29 private Model Gateway binding contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
