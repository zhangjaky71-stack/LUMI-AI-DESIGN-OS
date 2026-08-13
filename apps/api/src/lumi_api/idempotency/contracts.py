from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

_TRANSIENT_REQUEST_KEYS = frozenset(
    {
        "trace_id",
        "traceid",
        "request_id",
        "span_id",
        "retry_attempt",
        "transport_attempt",
    }
)


class OperationStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"
    AMBIGUOUS = "ambiguous"


class ClaimDecision(StrEnum):
    EXECUTE = "execute"
    REPLAY = "replay"
    WAIT = "wait"
    RECONCILE = "reconcile"
    RETRY_SAFE = "retry_safe"
    FINAL_FAILURE = "final_failure"
    AMBIGUOUS = "ambiguous"


class ProviderState(StrEnum):
    SUCCEEDED = "succeeded"
    PENDING = "pending"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CompensationStrategy(StrEnum):
    COMPENSATABLE = "compensatable"
    NON_COMPENSATABLE = "non_compensatable"
    REVERSIBLE_BY_NEW_OPERATION = "reversible_by_new_operation"


@dataclass(frozen=True, slots=True)
class IdempotencyContext:
    organization_id: UUID
    operation_type: str
    idempotency_key: str
    request: Any
    business_scope_id: UUID | None = None
    lease_seconds: int = 60

    def __post_init__(self) -> None:
        if not self.operation_type or len(self.operation_type) > 100:
            raise ValueError("IDEMPOTENCY_OPERATION_TYPE_INVALID")
        if not self.idempotency_key or len(self.idempotency_key) > 512:
            raise ValueError("IDEMPOTENCY_KEY_INVALID")
        if not 5 <= self.lease_seconds <= 3600:
            raise ValueError("IDEMPOTENCY_LEASE_SECONDS_INVALID")

    @property
    def request_hash(self) -> str:
        return canonical_request_hash(self.request)


@dataclass(frozen=True, slots=True)
class ProviderReconciliation:
    state: ProviderState
    result_ref: str | None = None
    result_json: dict[str, Any] = field(default_factory=dict)
    response_status: int | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SideEffectResult:
    result_ref: str | None = None
    result_json: dict[str, Any] = field(default_factory=dict)
    response_status: int = 200


def canonical_request_hash(value: Any) -> str:
    normalized = _normalize(value, path="$", depth=0)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def deterministic_operation_key(*parts: object, prefix: str = "op") -> str:
    if not parts:
        raise ValueError("OPERATION_KEY_PARTS_REQUIRED")
    if not prefix or len(prefix) > 64:
        raise ValueError("OPERATION_KEY_PREFIX_INVALID")
    normalized = [
        _normalize(part, path=f"$[{index}]", depth=0)
        for index, part in enumerate(parts)
    ]
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def _normalize(value: Any, *, path: str, depth: int) -> Any:
    if depth > 20:
        raise ValueError("IDEMPOTENCY_REQUEST_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"IDEMPOTENCY_NON_FINITE_NUMBER:{path}")
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(f"IDEMPOTENCY_NAIVE_DATETIME:{path}")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"IDEMPOTENCY_NON_STRING_KEY:{path}")
            if key.lower() in _TRANSIENT_REQUEST_KEYS:
                continue
            normalized[key] = _normalize(child, path=f"{path}.{key}", depth=depth + 1)
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize(child, path=f"{path}[{index}]", depth=depth + 1)
            for index, child in enumerate(value)
        ]
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"IDEMPOTENCY_BINARY_REQUEST_FORBIDDEN:{path}")
    raise ValueError(f"IDEMPOTENCY_UNSUPPORTED_VALUE:{path}:{type(value).__name__}")
