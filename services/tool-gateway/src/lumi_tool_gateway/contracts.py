from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_-]*)+$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_MAX_JSON_DEPTH = 24
_MAX_PURPOSE_LENGTH = 1000
_MAX_SUMMARY_LENGTH = 8000


class ToolRisk(StrEnum):
    READ_INTERNAL = "READ_INTERNAL"
    READ_EXTERNAL = "READ_EXTERNAL"
    WRITE_INTERNAL = "WRITE_INTERNAL"
    WRITE_EXTERNAL = "WRITE_EXTERNAL"
    DESTRUCTIVE = "DESTRUCTIVE"
    FINANCIAL = "FINANCIAL"
    PRIVILEGED = "PRIVILEGED"


class ToolRuntime(StrEnum):
    NATIVE = "native"
    MCP = "mcp"
    SANDBOX = "sandbox"


class ToolIdempotency(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"


class ToolCallStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DENIED = "DENIED"
    FAILED = "FAILED"


class ApprovalDecision(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk: ToolRisk
    idempotency: ToolIdempotency
    permissions: frozenset[str]
    runtime: ToolRuntime
    timeout_seconds: float = 30.0
    max_inline_output_bytes: int = 64 * 1024
    sensitive_fields: frozenset[str] = frozenset()
    enabled: bool = True

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            raise ValueError("TOOL_NAME_INVALID")
        if not _SEMVER.fullmatch(self.version):
            raise ValueError("TOOL_VERSION_INVALID")
        if not self.description or len(self.description) > 2000:
            raise ValueError("TOOL_DESCRIPTION_INVALID")
        if not self.permissions:
            raise ValueError("TOOL_PERMISSIONS_REQUIRED")
        if not 0.1 <= self.timeout_seconds <= 3600:
            raise ValueError("TOOL_TIMEOUT_INVALID")
        if not 1024 <= self.max_inline_output_bytes <= 1024 * 1024:
            raise ValueError("TOOL_INLINE_OUTPUT_LIMIT_INVALID")
        _normalize_json(self.input_schema, path="$.input_schema", depth=0)
        _normalize_json(self.output_schema, path="$.output_schema", depth=0)
        for field_name in self.sensitive_fields:
            if not field_name or len(field_name) > 512:
                raise ValueError("TOOL_SENSITIVE_FIELD_INVALID")

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def major(self) -> int:
        return int(self.version.split(".", 1)[0])

    @property
    def is_write(self) -> bool:
        return self.risk in {
            ToolRisk.WRITE_INTERNAL,
            ToolRisk.WRITE_EXTERNAL,
            ToolRisk.DESTRUCTIVE,
            ToolRisk.FINANCIAL,
            ToolRisk.PRIVILEGED,
        }


@dataclass(frozen=True, slots=True)
class ToolPermissionContext:
    organization_id: UUID
    actor_id: str
    granted_permissions: frozenset[str]
    agent_allow_patterns: tuple[str, ...]
    parent_allow_patterns: tuple[str, ...] = ()
    organization_allow_patterns: tuple[str, ...] = ()
    organization_deny_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.actor_id or len(self.actor_id) > 255:
            raise ValueError("TOOL_ACTOR_INVALID")
        if not self.agent_allow_patterns:
            raise ValueError("TOOL_AGENT_ALLOWLIST_REQUIRED")
        for pattern in (
            *self.agent_allow_patterns,
            *self.parent_allow_patterns,
            *self.organization_allow_patterns,
            *self.organization_deny_patterns,
        ):
            if not pattern or len(pattern) > 255:
                raise ValueError("TOOL_PERMISSION_PATTERN_INVALID")


@dataclass(frozen=True, slots=True)
class ToolRequest:
    tool_call_id: UUID
    organization_id: UUID
    agent_run_id: UUID
    task_id: UUID
    actor_agent: str
    name: str
    version: str
    arguments: dict[str, Any]
    purpose: str
    permission_context: ToolPermissionContext
    idempotency_key: str | None = None
    approval_token: str | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            raise ValueError("TOOL_REQUEST_NAME_INVALID")
        if not self.version or len(self.version) > 64:
            raise ValueError("TOOL_REQUEST_VERSION_INVALID")
        if not self.actor_agent or len(self.actor_agent) > 255:
            raise ValueError("TOOL_ACTOR_AGENT_INVALID")
        if not self.purpose or len(self.purpose) > _MAX_PURPOSE_LENGTH:
            raise ValueError("TOOL_PURPOSE_INVALID")
        if self.organization_id != self.permission_context.organization_id:
            raise ValueError("TOOL_TENANT_CONTEXT_MISMATCH")
        if self.idempotency_key is not None:
            if not self.idempotency_key or len(self.idempotency_key) > 512:
                raise ValueError("TOOL_IDEMPOTENCY_KEY_INVALID")
        if self.approval_token is not None and len(self.approval_token) > 1024:
            raise ValueError("TOOL_APPROVAL_TOKEN_INVALID")
        if self.trace_id is not None and len(self.trace_id) > 128:
            raise ValueError("TOOL_TRACE_ID_INVALID")
        _normalize_json(self.arguments, path="$.arguments", depth=0)


@dataclass(frozen=True, slots=True)
class ToolAdapterOutput:
    data: Any
    summary: str = ""
    resource_refs: tuple[str, ...] = ()
    side_effect_ref: str | None = None

    def __post_init__(self) -> None:
        if len(self.summary) > _MAX_SUMMARY_LENGTH:
            raise ValueError("TOOL_OUTPUT_SUMMARY_TOO_LARGE")
        _normalize_json(self.data, path="$.tool_output", depth=0)
        for ref in self.resource_refs:
            if not ref or len(ref) > 2048:
                raise ValueError("TOOL_RESOURCE_REF_INVALID")
        if self.side_effect_ref is not None and len(self.side_effect_ref) > 2048:
            raise ValueError("TOOL_SIDE_EFFECT_REF_INVALID")


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_call_id: UUID
    status: ToolCallStatus
    resolved_name: str
    resolved_version: str
    summary: str = ""
    data: Any = field(default_factory=dict)
    resource_refs: tuple[str, ...] = ()
    truncated: bool = False
    full_result_ref: str | None = None
    replayed: bool = False
    approval_id: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.resolved_name and not _TOOL_NAME.fullmatch(self.resolved_name):
            raise ValueError("TOOL_RESULT_NAME_INVALID")
        if self.resolved_version and not _SEMVER.fullmatch(self.resolved_version):
            raise ValueError("TOOL_RESULT_VERSION_INVALID")
        if len(self.summary) > _MAX_SUMMARY_LENGTH:
            raise ValueError("TOOL_RESULT_SUMMARY_TOO_LARGE")
        _normalize_json(self.data, path="$.result_data", depth=0)


@dataclass(frozen=True, slots=True)
class ToolApproval:
    decision: ApprovalDecision
    approval_id: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSideEffectContext:
    organization_id: UUID
    operation_type: str
    idempotency_key: str
    request: dict[str, Any]
    business_scope_id: UUID


@dataclass(frozen=True, slots=True)
class ToolSideEffectResponse:
    output: ToolAdapterOutput
    replayed: bool
    operation_id: str | None = None


def canonical_json_bytes(value: Any) -> bytes:
    normalized = _normalize_json(value, path="$", depth=0)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalize_json(value: Any, *, path: str, depth: int) -> Any:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError(f"TOOL_JSON_TOO_DEEP:{path}")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"TOOL_JSON_NON_FINITE:{path}")
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"TOOL_JSON_NON_STRING_KEY:{path}")
            result[key] = _normalize_json(child, path=f"{path}.{key}", depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json(child, path=f"{path}[{index}]", depth=depth + 1)
            for index, child in enumerate(value)
        ]
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"TOOL_BINARY_VALUE_FORBIDDEN:{path}")
    raise ValueError(f"TOOL_JSON_VALUE_UNSUPPORTED:{path}:{type(value).__name__}")
