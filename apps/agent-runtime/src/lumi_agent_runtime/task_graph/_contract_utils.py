from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from uuid import UUID

_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_AGENT_REF = re.compile(
    r"^[a-z][a-z0-9_-]{0,62}@[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$"
)
_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,2040}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_EVENT_KEYS = {
    "prompt", "messages", "reasoning", "chain_of_thought", "scratchpad",
    "raw_response", "tool_output",
}


def _assert_acyclic(tasks: tuple[TaskDefinition, ...]) -> None:
    by_key = {task.task_key: task for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visited:
            return
        if key in visiting:
            raise ValueError(f"TASK_GRAPH_CYCLE:{key}")
        visiting.add(key)
        for dependency in by_key[key].depends_on:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)

    for key in sorted(by_key):
        visit(key)


def _key(value: str, code: str) -> None:
    if not _KEY.fullmatch(value):
        raise ValueError(code)


def _ref(value: str, code: str) -> None:
    if not _REF.fullmatch(value):
        raise ValueError(code)


def _unique(values: tuple[str, ...], code: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(code)


def _decimal(value: str, code: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(code) from exc
    if not result.is_finite():
        raise ValueError(code)
    return result


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _aware(value: datetime, code: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(code)


def _json_guard(value: Any) -> None:
    _jsonable(value)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("TASK_JSON_NON_FINITE")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("TASK_JSON_NON_FINITE")
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        _aware(value, "TASK_JSON_DATETIME_NAIVE")
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("TASK_JSON_NON_STRING_KEY")
            result[key] = _jsonable(child)
        return result
    if isinstance(value, (list, tuple)):
        return [_jsonable(child) for child in value]
    raise TypeError(f"TASK_JSON_UNSUPPORTED:{type(value).__name__}")


def _sha256(payload: Any) -> str:
    encoded = json.dumps(
        _jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contains_forbidden_event_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in _FORBIDDEN_EVENT_KEYS:
                return True
            if _contains_forbidden_event_key(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_event_key(child) for child in value)
    return False
