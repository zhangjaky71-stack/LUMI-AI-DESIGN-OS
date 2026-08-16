from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import import_module
from typing import Annotated, Any, Protocol

from .contracts import DeepAgentInvocationContext, ResolvedSubagent
from .errors import DeepAgentToolScopeError
from .ports import LargeResultOffloader, RunBudgetMeter

_LANGCHAIN_NAME = re.compile(r"[^a-zA-Z0-9_-]+")
_RESERVED_SCOPE_KEYS = {
    "organization_id",
    "org_id",
    "project_id",
    "agent_run_id",
    "run_id",
    "task_id",
    "operation_id",
    "actor_id",
    "permission_scope",
    "permissions",
}


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
        if not self.description or len(self.description) > 2_000:
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
        context: DeepAgentInvocationContext,
        actor_agent: str,
        payload: dict[str, Any],
        tool_call_id: str,
        idempotency_key: str,
    ) -> Any: ...


class LumiToolGatewayProvider:
    def __init__(
        self,
        *,
        definitions: ToolDefinitionReader,
        gateway: ToolGatewayInvoker,
        budget: RunBudgetMeter,
        offloader: LargeResultOffloader,
    ) -> None:
        self.definitions = definitions
        self.gateway = gateway
        self.budget = budget
        self.offloader = offloader

    async def tools_for_root(
        self,
        *,
        context: DeepAgentInvocationContext,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]:
        return tuple(
            await self._tool(
                canonical_name=name,
                context=context,
                actor_agent=context.root_agent,
            )
            for name in allowed_tools
        )

    async def tools_for_subagent(
        self,
        *,
        context: DeepAgentInvocationContext,
        definition: ResolvedSubagent,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]:
        return tuple(
            await self._tool(
                canonical_name=name,
                context=context,
                actor_agent=definition.agent_id,
            )
            for name in allowed_tools
        )

    async def _tool(
        self,
        *,
        canonical_name: str,
        context: DeepAgentInvocationContext,
        actor_agent: str,
    ) -> Any:
        if canonical_name not in context.permissions.allowed_tools:
            raise DeepAgentToolScopeError(f"tool not granted: {canonical_name}")
        definition = await self.definitions.resolve(canonical_name)
        if definition.name != canonical_name:
            raise DeepAgentToolScopeError(
                "tool catalog returned a different canonical name"
            )
        injected_type, structured_tool_type = _langchain_tool_types()

        async def call(payload: dict[str, Any], tool_call_id: str) -> Any:
            if not isinstance(payload, dict):
                raise DeepAgentToolScopeError("tool payload must be an object")
            reserved = _reserved_keys(payload)
            if reserved:
                raise DeepAgentToolScopeError(
                    "model payload attempted scope injection: "
                    + ",".join(sorted(reserved))
                )
            if not tool_call_id or len(tool_call_id) > 512:
                raise DeepAgentToolScopeError(
                    "stable framework tool_call_id is required"
                )
            await self.budget.before_tool_call(
                context=context,
                actor_agent=actor_agent,
                tool_name=definition.name,
            )
            key = _idempotency_key(
                context=context,
                actor_agent=actor_agent,
                definition=definition,
                tool_call_id=tool_call_id,
            )
            succeeded = False
            try:
                result = await self.gateway.invoke(
                    definition=definition,
                    context=context,
                    actor_agent=actor_agent,
                    payload=payload,
                    tool_call_id=tool_call_id,
                    idempotency_key=key,
                )
                normalized = await self.offloader.normalize(
                    context=context,
                    actor_agent=actor_agent,
                    tool_name=definition.name,
                    result=result,
                )
                succeeded = True
                return normalized
            finally:
                await self.budget.after_tool_call(
                    context=context,
                    actor_agent=actor_agent,
                    tool_name=definition.name,
                    succeeded=succeeded,
                )

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
                f"cannot build Tool Gateway wrapper for {definition.name}"
            ) from exc
        _mark(tool, "_lumi_tool_gateway_bound", True)
        _mark(tool, "_lumi_tool_name", definition.name)
        _mark(tool, "_lumi_tool_version", definition.version)
        return tool


def assert_gateway_tools(
    tools: tuple[Any, ...],
    expected: tuple[str, ...],
) -> tuple[str, ...]:
    versions: list[str] = []
    names: list[str] = []
    for tool in tools:
        if not bool(getattr(tool, "_lumi_tool_gateway_bound", False)):
            raise DeepAgentToolScopeError("tool bypasses NODE-25 Tool Gateway")
        name = getattr(tool, "_lumi_tool_name", None)
        version = getattr(tool, "_lumi_tool_version", None)
        if not isinstance(name, str) or not isinstance(version, str):
            raise DeepAgentToolScopeError("trusted tool lacks canonical identity")
        names.append(name)
        versions.append(f"{name}@{version}")
    if tuple(names) != expected:
        raise DeepAgentToolScopeError(
            f"unexpected tool scope: {names!r} != {expected!r}"
        )
    return tuple(versions)


def _reserved_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in _RESERVED_SCOPE_KEYS:
                found.add(key)
            found.update(_reserved_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_reserved_keys(child))
    return found


def _idempotency_key(
    *,
    context: DeepAgentInvocationContext,
    actor_agent: str,
    definition: BoundToolDefinition,
    tool_call_id: str,
) -> str:
    payload = ":".join(
        (
            str(context.agent_run_id),
            str(context.task_id or "no-task"),
            actor_agent,
            definition.name,
            definition.version,
            tool_call_id,
        )
    )
    return "deep-agent:" + hashlib.sha256(payload.encode()).hexdigest()


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
    if len(schema) > 6_000:
        schema = schema[:6_000] + "..."
    return (
        f"{definition.description}\n"
        f"Canonical LUMI tool: {definition.name}@{definition.version}. "
        "Pass business arguments only inside `payload`; tenant/run/task scope "
        "is server-injected. "
        f"Trusted input schema: {schema}"
    )


def _mark(obj: Any, name: str, value: Any) -> None:
    try:
        object.__setattr__(obj, name, value)
    except Exception as exc:
        raise DeepAgentToolScopeError(
            "cannot mark trusted Tool Gateway wrapper"
        ) from exc
