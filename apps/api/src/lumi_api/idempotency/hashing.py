from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

_EPHEMERAL_KEYS = frozenset(
    {
        "trace_id",
        "traceparent",
        "tracestate",
        "request_id",
        "x_request_id",
        "span_id",
        "retry_attempt",
        "delivery_attempt",
    }
)


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key).casefold() not in _EPHEMERAL_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive datetime is not canonical")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal is not canonical")
        normalized = value.normalize()
        return format(normalized, "f") if normalized != 0 else "0"
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not canonical")
        return json.loads(json.dumps(value, allow_nan=False))
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported canonical request value: {type(value).__name__}")


def canonical_request_json(value: Any) -> str:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_request_hash(value: Any) -> str:
    return hashlib.sha256(canonical_request_json(value).encode("utf-8")).hexdigest()


def deterministic_operation_key(
    *,
    organization_id: UUID,
    operation_type: str,
    business_scope_id: str,
    logical_key: str,
    policy_version: str = "v1",
) -> str:
    if not operation_type or not business_scope_id or not logical_key or not policy_version:
        raise ValueError("operation key components must be non-empty")
    material = "\x1f".join(
        (str(organization_id), operation_type, business_scope_id, logical_key, policy_version)
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"op_{digest}"
