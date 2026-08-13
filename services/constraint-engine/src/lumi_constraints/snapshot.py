from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from .model import Constraint
from .precedence import effective_constraints, precedence_key, scope_key


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(_plain(item) for item in value)
    return value


def constraint_snapshot_payload(constraints: Iterable[Constraint]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for constraint in effective_constraints(constraints):
        payload.append(
            {
                "id": constraint.id,
                "type": constraint.type,
                "scope": {
                    "node_ids": list(constraint.scope.node_ids),
                    "roles": list(constraint.scope.roles),
                    "frame_ids": list(constraint.scope.frame_ids),
                    "region": _plain(constraint.scope.region),
                },
                "severity": constraint.severity,
                "source": constraint.source,
                "source_precedence": precedence_key(constraint)[0],
                "priority": constraint.priority,
                "parameters": _plain(constraint.parameters),
                "override_policy": constraint.override_policy,
            }
        )
    return sorted(payload, key=lambda item: (item["type"], json.dumps(item["scope"], sort_keys=True), item["id"]))


def constraint_snapshot_hash(constraints: Iterable[Constraint]) -> str:
    encoded = json.dumps(
        constraint_snapshot_payload(constraints),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
