from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from copy import deepcopy
from typing import Any

from .models import DesignDocument

NON_SEMANTIC_METADATA_KEYS = {
    "updated_at",
    "last_accessed_at",
    "selection",
    "viewport",
    "cursor",
    "document_version",
    "applied_operation_ids",
    "command_history",
}
ROUND_SCALE = 1_000_000_000_000


def _canonical_number(value: int | float) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("IR_SCHEMA_INVALID: non-finite number")
    rounded = round(numeric * ROUND_SCALE) / ROUND_SCALE
    if abs(rounded) < 1 / ROUND_SCALE:
        return "0"
    if rounded.is_integer():
        return str(int(rounded))
    text = f"{rounded:.12f}".rstrip("0").rstrip(".")
    return text or "0"


def canonical_stringify(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_stringify(item) for item in value) + "]"
    if isinstance(value, dict):
        normalized = sorted(
            ((unicodedata.normalize("NFC", str(key)), child) for key, child in value.items()),
            key=lambda item: item[0],
        )
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False, separators=(',', ':'))}:"
            f"{canonical_stringify(child)}"
            for key, child in normalized
        ) + "}"
    raise ValueError(f"IR_SCHEMA_INVALID: unsupported canonical value {type(value).__name__}")


def canonicalize(document: DesignDocument) -> str:
    cloned = deepcopy(document)
    metadata = cloned.get("metadata", {})
    cloned["metadata"] = {
        key: value
        for key, value in metadata.items()
        if key not in NON_SEMANTIC_METADATA_KEYS
        and not key.startswith("ephemeral:")
        and not key.startswith("_ephemeral")
    }
    return canonical_stringify(cloned)


def hash_document(document: DesignDocument) -> str:
    return hashlib.sha256(canonicalize(document).encode("utf-8")).hexdigest()
