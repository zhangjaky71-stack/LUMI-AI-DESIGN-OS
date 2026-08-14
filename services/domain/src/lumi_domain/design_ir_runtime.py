from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

JsonObject = dict[str, Any]
Migration = Callable[[JsonObject], JsonObject]


class DesignIrRuntimeError(ValueError):
    def __init__(
        self,
        operation_id: str,
        code: str,
        message: str,
        target_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.operation_id = operation_id
        self.code = code
        self.target_id = target_id

    def as_dict(self) -> JsonObject:
        value: JsonObject = {
            "operation_id": self.operation_id,
            "code": self.code,
            "message": str(self),
        }
        if self.target_id is not None:
            value["target_id"] = self.target_id
        return value


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NON_FINITE_NUMBER")
        if value == 0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def document_version(document: JsonObject) -> int:
    metadata = document.get("metadata", {})
    value = metadata.get("document_version", 0) if isinstance(metadata, dict) else 0
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _error(
    operation: JsonObject,
    code: str,
    message: str,
    target_id: str | None = None,
) -> DesignIrRuntimeError:
    return DesignIrRuntimeError(str(operation.get("operation_id", "unknown")), code, message, target_id)


def _node(document: JsonObject, operation: JsonObject, node_id: str) -> JsonObject:
    nodes = document.setdefault("nodes", {})
    node = nodes.get(node_id)
    if not isinstance(node, dict):
        raise _error(operation, "TARGET_NOT_FOUND", f"Node {node_id} does not exist", node_id)
    return node


def _parent(document: JsonObject, operation: JsonObject, parent_id: str) -> JsonObject:
    nodes = document.setdefault("nodes", {})
    parent = nodes.get(parent_id)
    if not isinstance(parent, dict):
        raise _error(operation, "PARENT_NOT_FOUND", f"Parent {parent_id} does not exist", parent_id)
    return parent


def _children(node: JsonObject) -> list[str]:
    raw = node.get("children")
    if not isinstance(raw, list):
        raw = []
        node["children"] = raw
    return raw


def _insert_child(parent: JsonObject, child_id: str, index: Any = None) -> None:
    children = [value for value in _children(parent) if value != child_id]
    position = len(children)
    if isinstance(index, int) and not isinstance(index, bool):
        position = max(0, min(index, len(children)))
    children.insert(position, child_id)
    parent["children"] = children


def _descendants(document: JsonObject, root_id: str) -> set[str]:
    result: set[str] = set()
    root = document.get("nodes", {}).get(root_id, {})
    queue = list(root.get("children", [])) if isinstance(root, dict) else []
    while queue:
        current = queue.pop(0)
        if not isinstance(current, str) or current in result:
            continue
        result.add(current)
        node = document.get("nodes", {}).get(current, {})
        if isinstance(node, dict):
            queue.extend(node.get("children", []))
    return result


def _targets(operation: JsonObject) -> list[str]:
    values = operation.get("target_ids", [])
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise _error(operation, "INVALID_OPERATION", "target_ids must be a string array")
    return values


def _set_path(node: JsonObject, path: str, value: Any) -> None:
    keys = [key for key in path.split(".") if key]
    if not keys:
        raise ValueError("property path is empty")
    current = node
    for key in keys[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[keys[-1]] = deepcopy(value)


def _transform(node: JsonObject, patch: JsonObject) -> None:
    current = node.get("transform")
    current = current.copy() if isinstance(current, dict) else {}
    current.update(patch)
    node["transform"] = current


def _apply_create(document: JsonObject, operation: JsonObject, payload: JsonObject) -> None:
    raw = payload.get("node")
    if not isinstance(raw, dict):
        raise _error(operation, "INVALID_OPERATION", "CREATE_NODE payload.node must be an object")
    node = deepcopy(raw)
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id or not isinstance(node.get("kind"), str):
        raise _error(operation, "INVALID_OPERATION", "CREATE_NODE requires node.id and node.kind")
    nodes = document.setdefault("nodes", {})
    if node_id in nodes:
        raise _error(operation, "INVALID_OPERATION", f"Node {node_id} already exists", node_id)
    parent_id = payload.get("parent_id", node.get("parent_id"))
    if not isinstance(parent_id, str):
        raise _error(operation, "PARENT_NOT_FOUND", "CREATE_NODE requires a parent_id")
    parent = _parent(document, operation, parent_id)
    node["parent_id"] = parent_id
    node["children"] = list(node.get("children", [])) if isinstance(node.get("children"), list) else []
    nodes[node_id] = node
    _insert_child(parent, node_id, payload.get("index"))


def _apply_delete(document: JsonObject, operation: JsonObject) -> None:
    root_id = document.get("root_id")
    for node_id in _targets(operation):
        if node_id == root_id:
            raise _error(operation, "ROOT_MUTATION_FORBIDDEN", "The document root cannot be deleted", node_id)
        node = _node(document, operation, node_id)
        parent_id = node.get("parent_id")
        if isinstance(parent_id, str):
            parent = _parent(document, operation, parent_id)
            parent["children"] = [value for value in _children(parent) if value != node_id]
        for remove_id in [node_id, *_descendants(document, node_id)]:
            document["nodes"].pop(remove_id, None)


def _apply_property(document: JsonObject, operation: JsonObject, payload: JsonObject) -> None:
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise _error(operation, "INVALID_OPERATION", "SET_PROPERTY payload.path must be a string")
    for node_id in _targets(operation):
        if node_id == document.get("root_id") and path in {"id", "parent_id"}:
            raise _error(operation, "ROOT_MUTATION_FORBIDDEN", f"Cannot mutate root {path}", node_id)
        _set_path(_node(document, operation, node_id), path, payload.get("value"))


def _apply_reorder(document: JsonObject, operation: JsonObject, payload: JsonObject) -> None:
    for node_id in _targets(operation):
        node = _node(document, operation, node_id)
        parent_id = node.get("parent_id")
        if not isinstance(parent_id, str):
            raise _error(operation, "ROOT_MUTATION_FORBIDDEN", "Root cannot be reordered", node_id)
        _insert_child(_parent(document, operation, parent_id), node_id, payload.get("index"))


def _apply_reparent(document: JsonObject, operation: JsonObject, payload: JsonObject) -> None:
    parent_id = payload.get("parent_id")
    if not isinstance(parent_id, str):
        raise _error(operation, "INVALID_OPERATION", "REPARENT_NODE requires payload.parent_id")
    new_parent = _parent(document, operation, parent_id)
    for node_id in _targets(operation):
        if node_id == document.get("root_id"):
            raise _error(operation, "ROOT_MUTATION_FORBIDDEN", "Root cannot be reparented", node_id)
        node = _node(document, operation, node_id)
        if node_id == parent_id or parent_id in _descendants(document, node_id):
            raise _error(operation, "CYCLE_DETECTED", "Reparent would create a cycle", node_id)
        old_parent_id = node.get("parent_id")
        if isinstance(old_parent_id, str):
            old_parent = _parent(document, operation, old_parent_id)
            old_parent["children"] = [value for value in _children(old_parent) if value != node_id]
        node["parent_id"] = parent_id
        _insert_child(new_parent, node_id, payload.get("index"))


def _apply_one(
    document: JsonObject,
    operation: JsonObject,
    expected_version: int,
    applied: list[str],
) -> None:
    operation_id = str(operation.get("operation_id", "unknown"))
    if operation.get("expected_document_version") != expected_version:
        raise _error(operation, "VERSION_CONFLICT", f"Current document version is {expected_version}")
    payload = operation.get("payload", {})
    if not isinstance(payload, dict):
        raise _error(operation, "INVALID_OPERATION", "payload must be an object")
    _normalize(payload)
    operation_type = operation.get("type")

    if operation_type == "CREATE_NODE":
        _apply_create(document, operation, payload)
    elif operation_type == "DELETE_NODE":
        _apply_delete(document, operation)
    elif operation_type == "SET_PROPERTY":
        _apply_property(document, operation, payload)
    elif operation_type == "MOVE_NODE":
        for node_id in _targets(operation):
            node = _node(document, operation, node_id)
            current = node.get("transform", {})
            current = current if isinstance(current, dict) else {}
            x = payload.get("x")
            y = payload.get("y")
            dx = payload.get("dx", 0)
            dy = payload.get("dy", 0)
            _transform(
                node,
                {
                    "x": x if isinstance(x, (int, float)) else current.get("x", 0) + dx,
                    "y": y if isinstance(y, (int, float)) else current.get("y", 0) + dy,
                },
            )
    elif operation_type == "RESIZE_NODE":
        width, height = payload.get("width"), payload.get("height")
        if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            raise _error(operation, "INVALID_OPERATION", "RESIZE_NODE requires width and height")
        for node_id in _targets(operation):
            _transform(_node(document, operation, node_id), {"width": width, "height": height})
    elif operation_type == "ROTATE_NODE":
        rotation = payload.get("rotation_deg")
        if not isinstance(rotation, (int, float)):
            raise _error(operation, "INVALID_OPERATION", "ROTATE_NODE requires rotation_deg")
        for node_id in _targets(operation):
            _transform(_node(document, operation, node_id), {"rotation_deg": rotation})
    elif operation_type == "REORDER_NODE":
        _apply_reorder(document, operation, payload)
    elif operation_type == "REPARENT_NODE":
        _apply_reparent(document, operation, payload)
    elif operation_type == "REPLACE_ASSET":
        asset_id = payload.get("asset_id")
        if not isinstance(asset_id, str):
            raise _error(operation, "INVALID_OPERATION", "REPLACE_ASSET requires asset_id")
        for node_id in _targets(operation):
            _node(document, operation, node_id)["asset_id"] = asset_id
    elif operation_type == "SET_TEXT":
        content = payload.get("content")
        if not isinstance(content, str):
            raise _error(operation, "INVALID_OPERATION", "SET_TEXT requires content")
        for node_id in _targets(operation):
            _node(document, operation, node_id)["content"] = content
    elif operation_type == "APPLY_STYLE":
        style_refs = payload.get("style_refs")
        if not isinstance(style_refs, list):
            style_ref = payload.get("style_ref")
            style_refs = [style_ref] if isinstance(style_ref, str) else []
        if not style_refs or not all(isinstance(value, str) for value in style_refs):
            raise _error(operation, "INVALID_OPERATION", "APPLY_STYLE requires style refs")
        for node_id in _targets(operation):
            _node(document, operation, node_id)["style_refs"] = list(style_refs)
    elif operation_type == "BATCH":
        nested = payload.get("operations")
        if not isinstance(nested, list):
            raise _error(operation, "INVALID_OPERATION", "BATCH payload.operations must be an array")
        for child in nested:
            if not isinstance(child, dict):
                raise _error(operation, "INVALID_OPERATION", "BATCH operations must be objects")
            _apply_one(document, child, expected_version, applied)
    else:
        raise _error(operation, "UNSUPPORTED_OPERATION", f"Unsupported operation {operation_type}")
    applied.append(operation_id)


def execute_operations(document: JsonObject, operations: list[JsonObject]) -> JsonObject:
    """Apply one atomic transaction without mutating the caller's document."""
    previous_version = document_version(document)
    working = deepcopy(document)
    applied: list[str] = []
    try:
        for operation in operations:
            _apply_one(working, operation, previous_version, applied)
    except DesignIrRuntimeError as exc:
        return {
            "ok": False,
            "document": document,
            "failures": [exc.as_dict()],
            "previous_version": previous_version,
            "document_version": previous_version,
        }
    metadata = working.setdefault("metadata", {})
    metadata["document_version"] = previous_version + 1
    return {
        "ok": True,
        "document": working,
        "applied_operation_ids": applied,
        "previous_version": previous_version,
        "document_version": previous_version + 1,
    }


@dataclass(slots=True)
class DesignIrMigrationRegistry:
    steps: dict[str, tuple[str, Migration]]

    def __init__(self) -> None:
        self.steps = {}

    def register(self, source: str, target: str, migration: Migration) -> None:
        if source == target:
            raise ValueError("Migration must advance schema_version")
        if source in self.steps:
            raise ValueError(f"Migration from {source} already registered")
        self.steps[source] = (target, migration)

    def migrate(self, document: JsonObject, target_version: str) -> JsonObject:
        current = deepcopy(document)
        visited: set[str] = set()
        while current.get("schema_version") != target_version:
            version = str(current.get("schema_version"))
            if version in visited:
                raise ValueError(f"Migration cycle detected at {version}")
            visited.add(version)
            step = self.steps.get(version)
            if step is None:
                raise ValueError(f"No Design IR migration path from {version} to {target_version}")
            next_version, migration = step
            provenance = deepcopy(current.get("metadata", {}).get("provenance"))
            migrated = migration(deepcopy(current))
            if migrated.get("schema_version") != next_version:
                raise ValueError(f"Migration {version} -> {next_version} returned wrong version")
            if provenance is not None:
                migrated.setdefault("metadata", {}).setdefault("provenance", provenance)
            current = migrated
        return current


def semantic_diff(before: JsonObject, after: JsonObject) -> JsonObject:
    before_nodes = before.get("nodes", {})
    after_nodes = after.get("nodes", {})
    before_ids, after_ids = set(before_nodes), set(after_nodes)
    added = sorted(after_ids - before_ids)
    removed = sorted(before_ids - after_ids)
    changes: list[JsonObject] = []
    for node_id in added:
        changes.append({"kind": "NODE_ADDED", "node_id": node_id})
    for node_id in removed:
        changes.append({"kind": "NODE_REMOVED", "node_id": node_id})
    changed_ids: list[str] = []
    for node_id in sorted(before_ids & after_ids):
        left, right = before_nodes[node_id], after_nodes[node_id]
        if canonical_json(left) == canonical_json(right):
            continue
        changed_ids.append(node_id)
        for prop, kind in (
            ("transform", "GEOMETRY_CHANGED"),
            ("children", "ORDER_CHANGED"),
            ("constraint_refs", "CONSTRAINT_CHANGED"),
            ("asset_id", "ASSET_REPLACED"),
            ("content", "TEXT_CHANGED"),
        ):
            if canonical_json(left.get(prop)) != canonical_json(right.get(prop)):
                changes.append({"kind": kind, "node_id": node_id, "property": prop})
    if before.get("schema_version") != after.get("schema_version"):
        changes.append({"kind": "SCHEMA_VERSION_CHANGED", "property": "schema_version"})
    return {
        "changed": bool(changes),
        "changes": changes,
        "added_node_ids": added,
        "removed_node_ids": removed,
        "changed_node_ids": changed_ids,
    }
