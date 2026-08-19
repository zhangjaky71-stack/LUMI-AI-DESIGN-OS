from __future__ import annotations

import asyncio
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Sequence
from uuid import UUID, uuid5

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from lumi_model_gateway import Capability, ModelRequest, ModelResult
from lumi_model_gateway.http_transport import HttpModelGatewayClient
from pydantic import ConfigDict

from .contracts import DeepAgentInvocationContext, SubagentInvocationContext
from .providers import ProfileModelProvider, mark_model_gateway_bound

_Context = DeepAgentInvocationContext | SubagentInvocationContext


class ModelGatewayChatModel(BaseChatModel):
    """LangChain chat-model bridge that can only execute through NODE-22 HTTP."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: HttpModelGatewayClient
    invocation_context: _Context
    model_profile: str
    bound_tools: tuple[dict[str, Any], ...] = ()
    tool_choice: str = "auto"
    parallel_tool_calls: bool | None = None

    @property
    def _llm_type(self) -> str:
        return "lumi-model-gateway"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_profile": self.model_profile, "transport": "node-22-http"}

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> ModelGatewayChatModel:
        strict = kwargs.pop("strict", None)
        parallel = kwargs.pop("parallel_tool_calls", None)
        if kwargs:
            names = ",".join(sorted(kwargs))
            raise ValueError(f"MODEL_GATEWAY_LANGCHAIN_BIND_OPTION_UNSUPPORTED:{names}")
        if parallel is not None and not isinstance(parallel, bool):
            raise ValueError("MODEL_GATEWAY_LANGCHAIN_PARALLEL_TOOLS_INVALID")
        normalized_tools = tuple(_normalize_langchain_tool(tool, strict=strict) for tool in tools)
        names = [tool["name"] for tool in normalized_tools]
        if len(set(names)) != len(names):
            raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_DUPLICATE")
        choice = _normalize_tool_choice(tool_choice)
        bound = self.model_copy(
            update={
                "bound_tools": normalized_tools,
                "tool_choice": choice,
                "parallel_tool_calls": parallel,
            }
        )
        return mark_model_gateway_bound(bound)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        return _run_sync(self._generate_async(messages, stop=stop, **kwargs))

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        return await self._generate_async(messages, stop=stop, **kwargs)

    async def _generate_async(
        self,
        messages: list[BaseMessage],
        *,
        stop: list[str] | None,
        **kwargs: Any,
    ) -> ChatResult:
        if stop:
            raise ValueError("MODEL_GATEWAY_LANGCHAIN_STOP_UNSUPPORTED")
        if kwargs:
            names = ",".join(sorted(kwargs))
            raise ValueError(f"MODEL_GATEWAY_LANGCHAIN_CALL_OPTION_UNSUPPORTED:{names}")
        wire_messages = [_encode_message(message, index=index) for index, message in enumerate(messages)]
        inputs: dict[str, Any] = {"messages": wire_messages}
        if self.bound_tools:
            inputs["tools"] = list(self.bound_tools)
            inputs["tool_choice"] = self.tool_choice
            if self.parallel_tool_calls is not None:
                inputs["parallel_tool_calls"] = self.parallel_tool_calls

        budget_limit = _budget_limit(self.invocation_context)
        operation_id = _turn_operation_id(
            self.invocation_context.operation_id,
            model_profile=self.model_profile,
            messages=wire_messages,
            tools=self.bound_tools,
            tool_choice=self.tool_choice,
        )
        request = ModelRequest(
            organization_id=self.invocation_context.organization_id,
            project_id=self.invocation_context.project_id,
            task_id=self.invocation_context.task_id,
            agent_run_id=self.invocation_context.agent_run_id,
            operation_id=operation_id,
            capability=Capability.LLM_REASONING,
            budget_limit_usd=budget_limit,
            inputs=inputs,
            constraints={"model_profile": self.model_profile},
            trace_id=self.invocation_context.trace_id,
        )
        result = await self.client.invoke(request)
        message = _decode_result(result)
        return ChatResult(generations=[ChatGeneration(message=message)])


def build_profile_model_provider_from_env() -> ProfileModelProvider:
    base_url = _required_env("LUMI_MODEL_GATEWAY_URL", max_length=2048)
    secret = _required_env("LUMI_MODEL_GATEWAY_AUTH_SECRET", max_length=8192)
    client = HttpModelGatewayClient(
        base_url=base_url,
        auth_secret=secret,
        caller_service="agent-runtime",
    )

    async def resolver(model_profile: str, context: _Context) -> ModelGatewayChatModel:
        model = ModelGatewayChatModel(
            client=client,
            invocation_context=context,
            model_profile=model_profile,
            disable_streaming=True,
        )
        return mark_model_gateway_bound(model)

    return ProfileModelProvider(resolver)


def _normalize_langchain_tool(tool: Any, *, strict: Any) -> dict[str, Any]:
    if strict is not None and not isinstance(strict, bool):
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_STRICT_INVALID")
    converted = convert_to_openai_tool(tool, strict=strict)
    if not isinstance(converted, dict) or converted.get("type") != "function":
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_ONLY_FUNCTION_TOOLS_SUPPORTED")
    function = converted.get("function")
    if isinstance(function, dict):
        definition = function
    else:
        definition = converted
    name = definition.get("name")
    description = definition.get("description", "")
    parameters = definition.get("parameters", {"type": "object", "properties": {}})
    strict_value = definition.get("strict", converted.get("strict", False))
    if not isinstance(name, str) or not name:
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_NAME_INVALID")
    if not isinstance(description, str):
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_DESCRIPTION_INVALID")
    if not isinstance(parameters, dict):
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_PARAMETERS_INVALID")
    if strict_value is None:
        strict_value = False
    if not isinstance(strict_value, bool):
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_STRICT_INVALID")
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
        "strict": strict_value,
    }


def _normalize_tool_choice(value: str | None) -> str:
    if value is None or value == "auto":
        return "auto"
    if value in {"any", "required"}:
        return "required"
    if value == "none":
        return "none"
    raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_CHOICE_UNSUPPORTED")


def _encode_message(message: BaseMessage, *, index: int) -> dict[str, Any]:
    content = _text_content(message.content, path=f"messages[{index}].content")
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": content}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": content}
    if isinstance(message, ToolMessage):
        if not message.tool_call_id:
            raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_CALL_ID_REQUIRED")
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": content,
        }
    if isinstance(message, AIMessage):
        tool_calls: list[dict[str, Any]] = []
        for call in message.tool_calls:
            call_id = call.get("id")
            name = call.get("name")
            args = call.get("args")
            if not isinstance(call_id, str) or not call_id:
                raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_CALL_ID_INVALID")
            if not isinstance(name, str) or not name:
                raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_CALL_NAME_INVALID")
            if not isinstance(args, dict):
                raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_CALL_ARGS_INVALID")
            tool_calls.append({"id": call_id, "name": name, "args": args})
        return {
            "role": "assistant",
            "content": content or None,
            "tool_calls": tool_calls,
        }
    raise ValueError(f"MODEL_GATEWAY_LANGCHAIN_MESSAGE_UNSUPPORTED:{type(message).__name__}")


def _text_content(value: Any, *, path: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for index, item in enumerate(value):
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict) and item.get("type") in {"text", "input_text", "output_text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
            raise ValueError(f"MODEL_GATEWAY_LANGCHAIN_MULTIMODAL_UNSUPPORTED:{path}[{index}]")
        return "".join(parts)
    raise ValueError(f"MODEL_GATEWAY_LANGCHAIN_CONTENT_UNSUPPORTED:{path}")


def _decode_result(result: ModelResult) -> AIMessage:
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    refusal_parts: list[str] = []
    for output in result.outputs:
        if output.kind == "text" and isinstance(output.value, str):
            text_parts.append(output.value)
            continue
        if output.kind == "tool_call" and isinstance(output.value, dict):
            call_id = output.value.get("id")
            name = output.value.get("name")
            args = output.value.get("args")
            if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(args, dict):
                raise ValueError("MODEL_GATEWAY_LANGCHAIN_TOOL_OUTPUT_INVALID")
            tool_calls.append({"id": call_id, "name": name, "args": args, "type": "tool_call"})
            continue
        if output.kind == "refusal" and isinstance(output.value, str):
            refusal_parts.append(output.value)
            continue
        raise ValueError(f"MODEL_GATEWAY_LANGCHAIN_OUTPUT_UNSUPPORTED:{output.kind}")
    content = "".join(text_parts)
    if refusal_parts and not content:
        content = "\n".join(refusal_parts)
    metadata = {
        "provider": result.provider,
        "model": result.model,
        "provider_request_id": result.provider_request_id,
        "finish_reason": result.finish_reason,
        "cost_usd": (
            format(result.cost.amount_usd, "f") if result.cost.amount_usd is not None else None
        ),
        "cost_confidence": result.cost.confidence.value,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "total_tokens": result.usage.total_tokens,
    }
    return AIMessage(
        content=content,
        tool_calls=tool_calls,
        response_metadata=metadata,
        additional_kwargs={"refusals": refusal_parts} if refusal_parts else {},
    )


def _turn_operation_id(
    parent_operation_id: UUID,
    *,
    model_profile: str,
    messages: list[dict[str, Any]],
    tools: tuple[dict[str, Any], ...],
    tool_choice: str,
) -> UUID:
    payload = json.dumps(
        {
            "model_profile": model_profile,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return uuid5(parent_operation_id, f"model-turn:{digest}")


def _budget_limit(context: _Context) -> Decimal | None:
    raw = getattr(context, "budget_limit_usd", None)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_BUDGET_INVALID")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_BUDGET_INVALID") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("MODEL_GATEWAY_LANGCHAIN_BUDGET_INVALID")
    return value


def _required_env(name: str, *, max_length: int) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"MODEL_GATEWAY_AGENT_REQUIRED_ENV_INVALID:{name}")
    return value


def _run_sync(awaitable: Awaitable[ChatResult]) -> ChatResult:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="lumi-model-gateway-sync") as pool:
        return pool.submit(lambda: asyncio.run(awaitable)).result()
