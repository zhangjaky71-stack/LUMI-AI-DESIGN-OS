from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any
from uuid import uuid4

from .contracts import DeepAgentInvocationContext, SubagentInvocationContext
from .errors import DeepAgentToolScopeError
from .tooling import BoundToolDefinition


class StaticToolDefinitionReader:
    """Trusted immutable tool catalog snapshot supplied by the composition root."""

    def __init__(self, definitions: tuple[BoundToolDefinition, ...]) -> None:
        self._definitions: dict[str, BoundToolDefinition] = {}
        for definition in definitions:
            if definition.name in self._definitions:
                raise ValueError(f"DEEP_TOOL_DUPLICATE:{definition.name}")
            self._definitions[definition.name] = definition

    async def resolve(self, name: str) -> BoundToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise DeepAgentToolScopeError(f"tool not found in trusted snapshot: {name}") from exc


class Node25ToolGatewayInvoker:
    """Dynamic adapter that keeps NODE-25 server internals out of Deep Agent runtime."""

    def __init__(self, client: Any) -> None:
        self.client = client

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
    ) -> Any:
        try:
            contracts = import_module("lumi_tool_gateway.contracts")
            permission_type = getattr(contracts, "ToolPermissionContext")
            request_type = getattr(contracts, "ToolRequest")
        except (ImportError, AttributeError) as exc:
            raise DeepAgentToolScopeError(
                "NODE-25 Tool Gateway contracts are unavailable"
            ) from exc

        permission_kwargs = {
            "organization_id": context.organization_id,
            "actor_id": context.actor_id,
            "granted_permissions": context.granted_permissions,
            "agent_allow_patterns": context.allowed_tools,
            "parent_allow_patterns": parent_allowed_tools,
        }
        permission = _construct_supported(permission_type, permission_kwargs)
        request_kwargs = {
            "tool_call_id": uuid4(),
            "organization_id": context.organization_id,
            "project_id": context.project_id,
            "agent_run_id": context.agent_run_id,
            "task_id": context.task_id,
            "actor_agent": actor_agent,
            "name": definition.name,
            "version": definition.version,
            "arguments": payload,
            "purpose": f"deep-agent:{context.root_agent}:{actor_agent}:{tool_call_id}",
            "permission_context": permission,
            "idempotency_key": idempotency_key,
            "trace_id": context.trace_id,
        }
        request = _construct_supported(request_type, request_kwargs)
        try:
            result = await self.client.invoke(request)
        except Exception:
            # NODE-25 is responsible for sanitized tool errors. Do not concatenate raw
            # provider/tool exception text into a second Deep Agent error channel.
            raise
        return _tool_result_payload(result)


def _construct_supported(type_: Any, values: dict[str, Any]) -> Any:
    try:
        parameters = inspect.signature(type_).parameters
    except (TypeError, ValueError) as exc:
        raise DeepAgentToolScopeError("cannot inspect NODE-25 contract constructor") from exc
    required = {
        name
        for name, parameter in parameters.items()
        if name != "self"
        and parameter.default is inspect.Parameter.empty
        and parameter.kind
        not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    }
    missing = required - set(values)
    if missing:
        raise DeepAgentToolScopeError(
            "NODE-25 contract requires unsupported fields: " + ",".join(sorted(missing))
        )
    kwargs = {name: value for name, value in values.items() if name in parameters}
    try:
        return type_(**kwargs)
    except Exception as exc:
        raise DeepAgentToolScopeError("cannot construct NODE-25 tool request") from exc


def _tool_result_payload(result: Any) -> dict[str, Any]:
    data = getattr(result, "data", None)
    payload: dict[str, Any] = {"data": data}
    for source, target in (
        ("full_result_ref", "full_result_ref"),
        ("replayed", "replayed"),
        ("resolved_tool", "resolved_tool"),
        ("status", "status"),
    ):
        value = getattr(result, source, None)
        if value is not None:
            payload[target] = value.value if hasattr(value, "value") else value
    return payload
