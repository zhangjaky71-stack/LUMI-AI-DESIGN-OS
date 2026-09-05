from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from copy import deepcopy
from typing import Any

EPHEMERAL_METADATA_KEYS = {
    "updated_at",
    "last_accessed_at",
    "selection",
    "viewport",
    "cursor",
}


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NON_FINITE_NUMBER")
        if value == 0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(key)): _normalize(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    return value


def canonical_stringify(value: Any) -> str:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_stringify(value).encode("utf-8")).hexdigest()


def _without_ephemeral_metadata(document: dict[str, Any]) -> dict[str, Any]:
    cloned = deepcopy(document)
    metadata = cloned.get("metadata")
    if isinstance(metadata, dict):
        cloned["metadata"] = {
            key: value
            for key, value in metadata.items()
            if key not in EPHEMERAL_METADATA_KEYS
            and not key.startswith("ephemeral:")
            and not key.startswith("_ephemeral")
        }
    return cloned


def canonical_document(document: dict[str, Any]) -> str:
    return canonical_stringify(_without_ephemeral_metadata(document))


def hash_document(document: dict[str, Any]) -> str:
    return canonical_sha256(_without_ephemeral_metadata(document))
