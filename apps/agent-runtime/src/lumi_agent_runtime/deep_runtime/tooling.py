from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import import_module
from typing import Annotated, Any, Protocol

from .contracts import DeepAgentInvocationContext, SubagentInvocationContext
from .errors import DeepAgentToolScopeError

_LANGCHAIN_NAME = re.compile(r"[^a-zA-Z0-9_-]+")


@dataclass(frozen=True, slots=True)
class BoundToolDefinition:
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 255:
            raise ValueError("DEEP_TOOL_NAME_INVALID")
        if not self.version or len(self.version) > 100:
            raise ValueError("DEEP_TOOL_VERSION_INVALID")
        if not self.description or len(self.description) > 2000:
            raise ValueError("DEEP_TOOL_DESCRIPTION_INVALID")
        if not isinstance(self.input_schema, dict):
            raise ValueError("DEEP_TOOL_SCHEMA_INVALID")


class ToolDefinitionReader(Protocol):
    async def resolve(self, name: str) -> BoundToolDefinition: ...


class ToolGatewayInvoker(Protocol):
    async def invoke(
        self,
        *,
        definition: BoundToolDefinition,
        context: DeepAgentInvocationContext | SubagentInvocationContext,
        actor_agent: str,
        parent_allowed_tools: tuple[str, ...] | None,
        payload: dict[str, Any],
        tool_call_id: str,
        idempotency_key: str,
    ) -> Any: ...


class LumiToolGatewayProvider:
    """Builds Deep Agents tools whose only execution path is NODE-25 Tool Gateway."""

    def __init__(
        self,
        *,
        definitions: ToolDefinitionReader,
        gateway: ToolGatewayInvoker,
    ) -> None:
        self.definitions = definitions
        self.gateway = gateway

    async def tools_for_root(
        self,
        *,
        context: DeepAgentInvocationContext,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]:
        return tuple(
            [
                await self._tool(
                    canonical_name=name,
                    context=context,
                    actor_agent=context.root_agent,
                    parent_allowed_tools=None,
                )
                for name in allowed_tools
            ]
        )

    async def tools_for_subagent(
        self,
        *,
        context: SubagentInvocationContext,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]:
        return tuple(
            [
                await self._tool(
                    canonical_name=name,
                    context=context,
                    actor_agent=context.subagent_name,
                    parent_allowed_tools=context.parent_allowed_tools,
                )
                for name in allowed_tools
            ]
        )

    async def _tool(
        self,
        *,
        canonical_name: str,
        context: DeepAgentInvocationContext | SubagentInvocationContext,
        actor_agent: str,
        parent_allowed_tools: tuple[str, ...] | None,
    ) -> Any:
        definition = await self.definitions.resolve(canonical_name)
        if definition.name != canonical_name:
            raise DeepAgentToolScopeError("tool catalog returned a different canonical name")
        injected_type, structured_tool_type = _langchain_tool_types()

        async def call(
            payload: dict[str, Any],
            tool_call_id: str,
        ) -> Any:
            if not isinstance(payload, dict):
                raise DeepAgentToolScopeError("Deep Agent tool payload must be an object")
            if not tool_call_id or len(tool_call_id) > 512:
                raise DeepAgentToolScopeError("stable LangChain tool_call_id is required")
            idempotency_key = f"deep-agent:{context.agent_run_id}:{tool_call_id}"
            return await self.gateway.invoke(
                definition=definition,
                context=context,
                actor_agent=actor_agent,
                parent_allowed_tools=parent_allowed_tools,
                payload=payload,
                tool_call_id=tool_call_id,
                idempotency_key=idempotency_key,
            )

        # LangChain hides InjectedToolCallId from the model-facing schema while still
        # supplying the stable framework tool-call identity at execution time.
        call.__annotations__ = {
            "payload": dict[str, Any],
            "tool_call_id": Annotated[str, injected_type],
            "return": Any,
        }
        call.__name__ = _langchain_name(definition.name)
        call.__doc__ = _trusted_description(definition)
        try:
            tool = structured_tool_type.from_function(
                coroutine=call,
                name=call.__name__,
                description=call.__doc__,
            )
        except Exception as exc:
            raise DeepAgentToolScopeError(
                f"cannot build LangChain tool wrapper for {definition.name}"
            ) from exc
        _mark(tool, "_lumi_tool_gateway_bound", True)
        _mark(tool, "_lumi_tool_name", definition.name)
        _mark(tool, "_lumi_tool_version", definition.version)
        return tool


def _langchain_tool_types() -> tuple[Any, Any]:
    try:
        tools_module = import_module("langchain_core.tools")
        injected = getattr(tools_module, "InjectedToolCallId")
        structured = getattr(tools_module, "StructuredTool")
    except (ImportError, AttributeError) as exc:
        raise DeepAgentToolScopeError(
            "current langchain-core StructuredTool/InjectedToolCallId is required"
        ) from exc
    return injected, structured


def _langchain_name(canonical: str) -> str:
    normalized = _LANGCHAIN_NAME.sub("__", canonical).strip("_")
    if not normalized:
        raise DeepAgentToolScopeError("canonical tool cannot map to LangChain name")
    return f"lumi__{normalized}"[:128]


def _trusted_description(definition: BoundToolDefinition) -> str:
    schema = json.dumps(
        definition.input_schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(schema) > 6000:
        schema = schema[:6000] + "..."
    return (
        f"{definition.description}\n"
        f"LUMI canonical tool: {definition.name}@{definition.version}. "
        "Pass all tool arguments inside the `payload` object. "
        f"Trusted input schema: {schema}"
    )


def _mark(obj: Any, name: str, value: Any) -> None:
    try:
        object.__setattr__(obj, name, value)
    except Exception as exc:
        raise DeepAgentToolScopeError("cannot mark trusted Tool Gateway wrapper") from exc
