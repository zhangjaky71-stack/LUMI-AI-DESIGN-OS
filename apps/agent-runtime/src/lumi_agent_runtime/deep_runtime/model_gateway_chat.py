from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar
from uuid import UUID, uuid5

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from lumi_model_gateway import Capability, ModelRequest, ResultStatus
from lumi_model_gateway.http_transport import HttpModelGatewayClient
from pydantic import Field

from .contracts import DeepAgentInvocationContext, SubagentInvocationContext
from .errors import DeepAgentModelBoundaryError
from .providers import ProfileModelProvider

_DEFAULT_CALLER_SERVICE = "agent-runtime"
_MAX_TOOL_COUNT = 128


class ModelGatewayChatModel(BaseChatModel):
    """LangChain chat-model facade over the private NODE-22 Model Gateway.

    This class deliberately contains no provider credential and no provider-native
    request schema. Every paid invocation crosses the signed internal HTTP boundary,
    then NODE-20/NODE-27 guards run inside model-gateway before the provider call.
    """

    base_url: str
    auth_secret: str = Field(repr=False, exclude=True)
    caller_service: str = _DEFAULT_CALLER_SERVICE
    model_profile: str
    organization_id: UUID
    project_id: UUID | None = None
    task_id: UUID | None = None
    agent_run_id: UUID | None = None
    parent_operation_id: UUID
    trace_id: str | None = None
    budget_limit_usd: str | None = None
    bound_tools: tuple[dict[str, Any], ...] = ()
    tool_choice: str = "auto"
    parallel_tool_calls: bool = True
    timeout_seconds: float = 90.0

    _lumi_model_gateway_bound: ClassVar[bool] = True

    @property
    def _llm_type(self) -> str:
        return "lumi-model-gateway"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model_profile": self.model_profile,
            "caller_service": self.caller_service,
            "base_url": self.base_url,
        }

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | bool | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelGatewayChatModel:
        if kwargs:
            raise DeepAgentModelBoundaryError(
                "unsupported model-gateway bind_tools options: "
                + ",".join(sorted(kwargs))
            )
        normalized = tuple(_normalize_tool(tool) for tool in tools)
        if len(normalized) > _MAX_TOOL_COUNT:
            raise DeepAgentModelBoundaryError("model tool count exceeds NODE-22 limit")
        return self.model_copy(
            update={
                "bound_tools": normalized,
                "tool_choice": _normalize_tool_choice(tool_choice),
            }
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop=stop, **kwargs))
        raise DeepAgentModelBoundaryError(
            "synchronous model invocation is forbidden inside a running event loop"
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        if stop:
            raise DeepAgentModelBoundaryError(
                "stop sequences are not enabled on the hosted NODE-22 adapter"
            )
        constraints: dict[str, Any] = {"model_profile": self.model_profile}
        max_output_tokens = kwargs.pop("max_output_tokens", kwargs.pop("max_tokens", None))
        if max_output_tokens is not None:
            if (
                isinstance(max_output_tokens, bool)
                or not isinstance(max_output_tokens, int)
                or not 1 <= max_output_tokens <= 100_000
            ):
                raise DeepAgentModelBoundaryError("invalid max_output_tokens")
            constraints["max_output_tokens"] = max_output_tokens
        if kwargs:
            raise DeepAgentModelBoundaryError(
                "unsupported model-gateway generation options: "
                + ",".join(sorted(kwargs))
            )

        wire_messages = [_message_to_wire(message) for message in messages]
        inputs: dict[str, Any] = {"messages": wire_messages}
        if self.bound_tools:
            inputs["tools"] = [dict(tool) for tool in self.bound_tools]
            inputs["tool_choice"] = self.tool_choice
            inputs["parallel_tool_calls"] = self.parallel_tool_calls

        operation_id = _derive_turn_operation_id(
            parent_operation_id=self.parent_operation_id,
            model_profile=self.model_profile,
            inputs=inputs,
            constraints=constraints,
        )
        request = ModelRequest(
            organization_id=self.organization_id,
            operation_id=operation_id,
            capability=Capability.LLM_REASONING,
            inputs=inputs,
            project_id=self.project_id,
            task_id=self.task_id,
            agent_run_id=self.agent_run_id,
            budget_limit_usd=_budget_decimal(self.budget_limit_usd),
            constraints=constraints,
            trace_id=self.trace_id,
        )
        client = HttpModelGatewayClient(
            base_url=self.base_url,
            auth_secret=self.auth_secret,
            caller_service=self.caller_service,
            timeout_seconds=self.timeout_seconds,
        )
        try:
            result = await client.invoke(request)
        except Exception as exc:
            if isinstance(exc, DeepAgentModelBoundaryError):
                raise
            raise DeepAgentModelBoundaryError(
                f"private Model Gateway invocation failed: {type(exc).__name__}"
            ) from exc
        if result.status != ResultStatus.SUCCEEDED:
            raise DeepAgentModelBoundaryError(
                f"Model Gateway returned non-terminal model status: {result.status.value}"
            )

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        refusals: list[str] = []
        for output in result.outputs:
            if output.kind == "text":
                if not isinstance(output.value, str):
                    raise DeepAgentModelBoundaryError("invalid text output from Model Gateway")
                text_parts.append(output.value)
            elif output.kind == "tool_call":
                tool_calls.append(_output_tool_call(output.value))
            elif output.kind == "refusal":
                if not isinstance(output.value, str):
                    raise DeepAgentModelBoundaryError("invalid refusal output from Model Gateway")
                refusals.append(output.value)
            else:
                raise DeepAgentModelBoundaryError(
                    f"unsupported LLM output kind from Model Gateway: {output.kind}"
                )
        if refusals and not text_parts and not tool_calls:
            raise DeepAgentModelBoundaryError("provider refused the Deep Agent model turn")

        usage_metadata: dict[str, int] | None = None
        if (
            result.usage.input_tokens is not None
            or result.usage.output_tokens is not None
            or result.usage.total_tokens is not None
        ):
            input_tokens = result.usage.input_tokens or 0
            output_tokens = result.usage.output_tokens or 0
            usage_metadata = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": result.usage.total_tokens or input_tokens + output_tokens,
            }
        message = AIMessage(
            content="".join(text_parts),
            tool_calls=tool_calls,
            usage_metadata=usage_metadata,
            response_metadata={
                "provider": result.provider,
                "model": result.model,
                "provider_request_id": result.provider_request_id,
                "finish_reason": result.finish_reason,
                "cost_usd": (
                    format(result.cost.amount_usd, "f")
                    if result.cost.amount_usd is not None
                    else None
                ),
                "price_snapshot_id": result.cost.price_snapshot_id,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


class HttpProfileModelProvider(ProfileModelProvider):
    """Production profile provider that always returns a signed HTTP gateway model."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        caller_service: str = _DEFAULT_CALLER_SERVICE,
        timeout_seconds: float = 90.0,
    ) -> None:
        if not base_url:
            raise DeepAgentModelBoundaryError("LUMI_MODEL_GATEWAY_URL is required")
        if not auth_secret:
            raise DeepAgentModelBoundaryError(
                "LUMI_MODEL_GATEWAY_AUTH_SECRET is required"
            )
        self.base_url = base_url
        self.auth_secret = auth_secret
        self.caller_service = caller_service
        self.timeout_seconds = timeout_seconds
        super().__init__(self._resolve)

    @classmethod
    def from_env(cls) -> HttpProfileModelProvider:
        return cls(
            base_url=os.getenv("LUMI_MODEL_GATEWAY_URL", ""),
            auth_secret=os.getenv("LUMI_MODEL_GATEWAY_AUTH_SECRET", ""),
            caller_service=_DEFAULT_CALLER_SERVICE,
        )

    async def _resolve(
        self,
        model_profile: str,
        context: DeepAgentInvocationContext | SubagentInvocationContext,
    ) -> ModelGatewayChatModel:
        return ModelGatewayChatModel(
            base_url=self.base_url,
            auth_secret=self.auth_secret,
            caller_service=self.caller_service,
            model_profile=model_profile,
            organization_id=context.organization_id,
            project_id=context.project_id,
            task_id=context.task_id,
            agent_run_id=context.agent_run_id,
            parent_operation_id=context.operation_id,
            trace_id=context.trace_id,
            budget_limit_usd=getattr(context, "budget_limit_usd", None),
            timeout_seconds=self.timeout_seconds,
        )


def _normalize_tool(tool: Any) -> dict[str, Any]:
    try:
        converted = convert_to_openai_tool(tool, strict=True)
    except Exception as exc:
        raise DeepAgentModelBoundaryError(
            f"tool cannot be converted to a function contract: {type(exc).__name__}"
        ) from exc
    if not isinstance(converted, dict) or converted.get("type") != "function":
        raise DeepAgentModelBoundaryError(
            "Deep Agents may bind function tools only through NODE-22"
        )
    function = converted.get("function")
    if isinstance(function, dict):
        source = function
    else:
        source = converted
    name = source.get("name")
    description = source.get("description", "")
    parameters = source.get("parameters")
    strict = source.get("strict", True)
    if not isinstance(name, str) or not name or len(name) > 128:
        raise DeepAgentModelBoundaryError("invalid function tool name")
    if not isinstance(description, str) or len(description) > 4096:
        raise DeepAgentModelBoundaryError(f"invalid description for tool {name}")
    if not isinstance(parameters, dict):
        raise DeepAgentModelBoundaryError(f"tool {name} has no JSON-schema parameters")
    if not isinstance(strict, bool):
        raise DeepAgentModelBoundaryError(f"tool {name} strict flag is invalid")
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
        "strict": strict,
    }


def _normalize_tool_choice(value: str | bool | dict[str, Any] | None) -> str:
    if value is None:
        return "auto"
    if value is True:
        return "required"
    if value is False:
        return "none"
    if isinstance(value, str):
        normalized = "required" if value == "any" else value
        if normalized in {"auto", "none", "required"}:
            return normalized
    raise DeepAgentModelBoundaryError(
        "specific provider-native tool_choice is not enabled on NODE-22"
    )


def _message_to_wire(message: BaseMessage) -> dict[str, Any]:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": _string_content(message, "system")}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": _string_content(message, "user")}
    if isinstance(message, ToolMessage):
        tool_call_id = message.tool_call_id
        if not isinstance(tool_call_id, str) or not tool_call_id:
            raise DeepAgentModelBoundaryError("ToolMessage requires tool_call_id")
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": _string_content(message, "tool"),
        }
    if isinstance(message, AIMessage):
        content = message.content
        if not isinstance(content, str):
            raise DeepAgentModelBoundaryError(
                "multimodal AIMessage content is not enabled on NODE-22"
            )
        tool_calls: list[dict[str, Any]] = []
        for raw in message.tool_calls:
            if not isinstance(raw, dict):
                raise DeepAgentModelBoundaryError("invalid LangChain tool call")
            call_id = raw.get("id")
            name = raw.get("name")
            args = raw.get("args")
            if not isinstance(call_id, str) or not call_id:
                raise DeepAgentModelBoundaryError("LangChain tool call requires id")
            if not isinstance(name, str) or not name:
                raise DeepAgentModelBoundaryError("LangChain tool call requires name")
            if not isinstance(args, dict):
                raise DeepAgentModelBoundaryError("LangChain tool call args must be an object")
            tool_calls.append({"id": call_id, "name": name, "args": args})
        if not content and not tool_calls:
            raise DeepAgentModelBoundaryError("AIMessage cannot be empty")
        return {"role": "assistant", "content": content, "tool_calls": tool_calls}
    raise DeepAgentModelBoundaryError(
        f"unsupported LangChain message type: {type(message).__name__}"
    )


def _string_content(message: BaseMessage, role: str) -> str:
    if not isinstance(message.content, str):
        raise DeepAgentModelBoundaryError(
            f"multimodal {role} content is not enabled on NODE-22"
        )
    return message.content


def _derive_turn_operation_id(
    *,
    parent_operation_id: UUID,
    model_profile: str,
    inputs: dict[str, Any],
    constraints: dict[str, Any],
) -> UUID:
    semantic = json.dumps(
        {
            "model_profile": model_profile,
            "inputs": inputs,
            "constraints": constraints,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(semantic).hexdigest()
    return uuid5(parent_operation_id, f"lumi-model-turn-v1:{digest}")


def _budget_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        budget = Decimal(value)
    except InvalidOperation as exc:
        raise DeepAgentModelBoundaryError("Deep Agent budget must be a decimal string") from exc
    if not budget.is_finite() or budget < 0:
        raise DeepAgentModelBoundaryError("Deep Agent budget must be finite and non-negative")
    return budget


def _output_tool_call(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"id", "name", "args"}:
        raise DeepAgentModelBoundaryError("invalid tool_call output from Model Gateway")
    call_id = value.get("id")
    name = value.get("name")
    args = value.get("args")
    if not isinstance(call_id, str) or not call_id:
        raise DeepAgentModelBoundaryError("Model Gateway tool_call id is invalid")
    if not isinstance(name, str) or not name:
        raise DeepAgentModelBoundaryError("Model Gateway tool_call name is invalid")
    if not isinstance(args, dict):
        raise DeepAgentModelBoundaryError("Model Gateway tool_call args are invalid")
    return {"id": call_id, "name": name, "args": args}
