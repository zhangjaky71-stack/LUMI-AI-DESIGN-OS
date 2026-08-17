from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from .contracts import RuntimeConstraint, ValidationPolicy


def touched_node_ids(operation: Mapping[str, Any]) -> set[str]:
    touched = {str(value) for value in operation.get("target_ids", ()) if value}
    payload = operation.get("payload", {})
    if isinstance(payload, Mapping):
        for key in ("parent_id", "new_parent_id", "frame_id", "mask_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                touched.add(value)
        node = payload.get("node")
        if isinstance(node, Mapping):
            for key in ("id", "parent_id", "mask_id"):
                value = node.get(key)
                if isinstance(value, str) and value:
                    touched.add(value)
    return touched


def dependency_expansion(
    document: Mapping[str, Any],
    touched: set[str],
    constraints: tuple[RuntimeConstraint, ...],
) -> set[str]:
    nodes = document.get("nodes", {})
    if not isinstance(nodes, Mapping):
        return set(touched)
    result = set(touched)
    queue: deque[str] = deque(touched)
    while queue:
        node_id = queue.popleft()
        node = nodes.get(node_id)
        if not isinstance(node, Mapping):
            continue
        parent_id = node.get("parent_id")
        if isinstance(parent_id, str) and parent_id not in result:
            result.add(parent_id)
        for child_id in node.get("children", ()):
            if isinstance(child_id, str) and child_id not in result:
                result.add(child_id)
        for key in ("mask_id", "asset_id", "source_artifact_version_id"):
            value = node.get(key)
            if isinstance(value, str) and value in nodes and value not in result:
                result.add(value)
    for constraint in constraints:
        if set(constraint.scope.node_ids) & result:
            result.update(constraint.scope.node_ids)
    return result


def impact_set(
    document: Mapping[str, Any],
    operation: Mapping[str, Any] | None,
    constraints: tuple[RuntimeConstraint, ...],
    policy: ValidationPolicy,
    *,
    force_full: bool = False,
) -> tuple[set[str], bool]:
    nodes = document.get("nodes", {})
    all_ids = set(nodes) if isinstance(nodes, Mapping) else set()
    if force_full or operation is None:
        return all_ids, True
    touched = touched_node_ids(operation)
    expanded = dependency_expansion(document, touched, constraints)
    threshold = min(
        policy.incremental_full_scan_node_limit,
        max(1, int(len(all_ids) * policy.incremental_full_scan_ratio)),
    )
    if len(expanded) >= threshold:
        return all_ids, True
    return expanded, False
