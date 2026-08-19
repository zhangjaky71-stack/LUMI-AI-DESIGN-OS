from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

_SECRET_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
)


@dataclass(frozen=True, slots=True)
class ToolAuditRecord:
    tool_call_id: str
    organization_id: str
    actor_id: str
    actor_agent: str
    resolved_tool: str
    risk: str
    purpose: str
    status: str
    trace_id: str | None
    arguments: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    replayed: bool = False
    side_effect_operation_id: str | None = None
    approval_id: str | None = None
    error_code: str | None = None


class MemoryAuditSink:
    def __init__(self) -> None:
        self.records: list[ToolAuditRecord] = []
        self._lock = asyncio.Lock()

    async def record(self, event: ToolAuditRecord) -> None:
        async with self._lock:
            self.records.append(event)


class NullAuditSink:
    async def record(self, event: ToolAuditRecord) -> None:
        del event


def redact_arguments(
    arguments: dict[str, Any],
    *,
    sensitive_fields: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    explicit = {item.strip(".") for item in sensitive_fields}

    def visit(value: Any, *, path: str) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                normalized_key = key.lower().replace("-", "_")
                if child_path in explicit or any(token in normalized_key for token in _SECRET_TOKENS):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = visit(child, path=child_path)
            return result
        if isinstance(value, list):
            return [visit(child, path=f"{path}[{index}]") for index, child in enumerate(value)]
        return value

    return visit(arguments, path="")
