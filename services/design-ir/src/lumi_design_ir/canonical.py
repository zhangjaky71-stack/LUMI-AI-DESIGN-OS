from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import StructuralValidationError


EPHEMERAL_METADATA_KEYS = frozenset(
    {
        "hover",
        "selection",
        "selection_marquee",
        "open_panel",
        "cursor",
        "cursor_location",
        "viewport",
        "camera",
        "dom_element_id",
        "pixi_texture_id",
    }
)


def _normalize(value: Any, *, path: str = "$") -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StructuralValidationError(f"non-finite number at {path}")
        # JSON round-trip gives one deterministic decimal representation for finite IEEE-754 values.
        if value == 0.0:
            return 0.0
        return float(repr(value))
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise StructuralValidationError(f"non-string object key at {path}")
            if path.endswith(".metadata") and key in EPHEMERAL_METADATA_KEYS:
                continue
            normalized[key] = _normalize(value[key], path=f"{path}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise StructuralValidationError(f"unsupported canonical value {type(value).__name__} at {path}")


def canonical_object(document: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize(document)
    if not isinstance(normalized, dict):
        raise StructuralValidationError("Design IR document must be an object")
    return normalized


def canonical_json(document: Mapping[str, Any]) -> str:
    return json.dumps(
        canonical_object(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(document: Mapping[str, Any]) -> str:
    payload = canonical_json(document).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
