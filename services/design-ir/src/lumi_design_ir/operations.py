from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .canonical import content_hash
from .errors import DocumentVersionConflict, OperationError
from .validation import validate_document


STRUCTURAL_SET_PROPERTY_ROOTS = frozenset({"id", "kind", "parent_id", "children"})


@dataclass(frozen=True, slots=True)
class AppliedOperation:
    document: dict[str, Any]
    document_version: int
    before_hash: str
    after_hash: str


def _require_targets(operation: dict[str, Any], *, count: int | None = None) -> list[str]:
    target_ids = operation.get("target_ids")
    if not isinstance(target_ids, list) or not all(isinstance(item, str) for item in target_ids):
        raise OperationError("target_ids must be a string list")
    if not target_ids and count != 0:
        raise OperationError("operation requires at least one target")
    if count is not None and len(target_ids) != count:
        raise OperationError(f"operation requires exactly {count} target(s)")
    return target_ids


def _require_payload(operation: dict[str, Any]) -> dict[str, Any]:
    payload = operation.get("payload")
    if not isinstance(payload, dict):
        raise OperationError("operation payload must be an object")
    return payload


def _require_node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    nodes = document["nodes"]
    node = nodes.get(node_id)
    if not isinstance(node, dict):
        raise OperationError(f"target node does not exist: {node_id}")
    return node


def _insert_child(parent: dict[str, Any], child_id: str, index: int) -> None:
    children = parent.get("children")
    if not isinstance(children, list):
        raise OperationError("parent children must be a list")
    if child_id in children:
        raise OperationError(f"child already attached: {child_id}")
    if index > len(children):
        raise OperationError(f"child index {index} exceeds parent size {len(children)}")
    children.insert(index, child_id)


def _remove_child(parent: dict[str, Any], child_id: str) -> None:
    children = parent.get("children")
    if not isinstance(children, list) or child_id not in children:
        raise OperationError(f"parent does not contain child: {child_id}")
    children.remove(child_id)


def _delete_subtree(document: dict[str, Any], node_id: str) -> None:
    if node_id == document["root_id"]:
        raise OperationError("DOCUMENT_ROOT cannot be deleted")
    node = _require_node(document, node_id)
    for child_id in list(node.get("children", [])):
        _delete_subtree(document, child_id)
    parent_id = node.get("parent_id")
    if isinstance(parent_id, str):
        _remove_child(_require_node(document, parent_id), node_id)
    del document["nodes"][node_id]


def _set_property(node: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if not parts or parts[0] in STRUCTURAL_SET_PROPERTY_ROOTS:
        raise OperationError(f"SET_PROPERTY cannot mutate structural field {path}")
    cursor: dict[str, Any] = node
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            raise OperationError(f"SET_PROPERTY path does not resolve to an object: {path}")
        cursor = next_value
    cursor[parts[-1]] = deepcopy(value)


def _apply_primitive(document: dict[str, Any], operation: dict[str, Any]) -> None:
    op_type = operation.get("type")
    payload = _require_payload(operation)

    if op_type == "CREATE_NODE":
        _require_targets(operation, count=0)
        raw_node = payload.get("node")
        parent_id = payload.get("parent_id")
        index = payload.get("index")
        if not isinstance(raw_node, dict) or not isinstance(parent_id, str) or not isinstance(index, int):
            raise OperationError("CREATE_NODE requires node, parent_id and integer index")
        node_id = raw_node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise OperationError("CREATE_NODE node.id is required")
        if node_id in document["nodes"]:
            raise OperationError(f"node already exists: {node_id}")
        parent = _require_node(document, parent_id)
        node = deepcopy(raw_node)
        node["parent_id"] = parent_id
        document["nodes"][node_id] = node
        _insert_child(parent, node_id, index)
        return

    if op_type == "DELETE_NODE":
        targets = _require_targets(operation)
        for target_id in list(targets):
            if target_id in document["nodes"]:
                _delete_subtree(document, target_id)
        return

    if op_type == "SET_PROPERTY":
        targets = _require_targets(operation)
        path = payload.get("path")
        if not isinstance(path, str) or not path:
            raise OperationError("SET_PROPERTY requires path")
        for target_id in targets:
            _set_property(_require_node(document, target_id), path, payload.get("value"))
        return

    if op_type == "MOVE_NODE":
        targets = _require_targets(operation)
        x = payload.get("x")
        y = payload.get("y")
        if not isinstance(x, (int, float)) or isinstance(x, bool):
            raise OperationError("MOVE_NODE x must be numeric")
        if not isinstance(y, (int, float)) or isinstance(y, bool):
            raise OperationError("MOVE_NODE y must be numeric")
        for target_id in targets:
            transform = _require_node(document, target_id).get("transform")
            if not isinstance(transform, dict):
                raise OperationError(f"node {target_id} has no transform")
            transform["x"] = x
            transform["y"] = y
        return

    if op_type == "RESIZE_NODE":
        targets = _require_targets(operation)
        width = payload.get("width")
        height = payload.get("height")
        if not isinstance(width, (int, float)) or isinstance(width, bool) or width < 0:
            raise OperationError("RESIZE_NODE width must be non-negative numeric")
        if not isinstance(height, (int, float)) or isinstance(height, bool) or height < 0:
            raise OperationError("RESIZE_NODE height must be non-negative numeric")
        for target_id in targets:
            node = _require_node(document, target_id)
            transform = node.get("transform")
            bounds = node.get("bounds")
            if not isinstance(transform, dict) or not isinstance(bounds, dict):
                raise OperationError(f"node {target_id} has no transform/bounds")
            transform["width"] = width
            transform["height"] = height
            bounds["width"] = width
            bounds["height"] = height
        return

    if op_type == "ROTATE_NODE":
        targets = _require_targets(operation)
        rotation = payload.get("rotation_deg")
        if not isinstance(rotation, (int, float)) or isinstance(rotation, bool):
            raise OperationError("ROTATE_NODE rotation_deg must be numeric")
        for target_id in targets:
            transform = _require_node(document, target_id).get("transform")
            if not isinstance(transform, dict):
                raise OperationError(f"node {target_id} has no transform")
            transform["rotation_deg"] = rotation
        return

    if op_type == "REORDER_NODE":
        target_id = _require_targets(operation, count=1)[0]
        index = payload.get("index")
        if not isinstance(index, int) or index < 0:
            raise OperationError("REORDER_NODE index must be a non-negative integer")
        node = _require_node(document, target_id)
        parent_id = node.get("parent_id")
        if not isinstance(parent_id, str):
            raise OperationError("root node cannot be reordered")
        parent = _require_node(document, parent_id)
        children = parent["children"]
        if index >= len(children):
            raise OperationError("REORDER_NODE index exceeds sibling range")
        children.remove(target_id)
        children.insert(index, target_id)
        return

    if op_type == "REPARENT_NODE":
        target_id = _require_targets(operation, count=1)[0]
        parent_id = payload.get("parent_id")
        index = payload.get("index")
        if not isinstance(parent_id, str) or not isinstance(index, int) or index < 0:
            raise OperationError("REPARENT_NODE requires parent_id and non-negative index")
        node = _require_node(document, target_id)
        if target_id == document["root_id"]:
            raise OperationError("root node cannot be reparented")
        old_parent_id = node.get("parent_id")
        if not isinstance(old_parent_id, str):
            raise OperationError("target node has no parent")
        old_parent = _require_node(document, old_parent_id)
        new_parent = _require_node(document, parent_id)
        _remove_child(old_parent, target_id)
        node["parent_id"] = parent_id
        _insert_child(new_parent, target_id, index)
        return

    if op_type == "REPLACE_ASSET":
        targets = _require_targets(operation)
        asset_id = payload.get("asset_id")
        if not isinstance(asset_id, str):
            raise OperationError("REPLACE_ASSET requires asset_id")
        for target_id in targets:
            node = _require_node(document, target_id)
            kind = node.get("kind")
            field = "image" if kind == "IMAGE" else "video" if kind == "VIDEO" else None
            if field is None or not isinstance(node.get(field), dict):
                raise OperationError(f"REPLACE_ASSET target must be IMAGE/VIDEO: {target_id}")
            node[field]["asset_id"] = asset_id
        return

    if op_type == "SET_TEXT":
        targets = _require_targets(operation)
        content = payload.get("content")
        if not isinstance(content, str):
            raise OperationError("SET_TEXT requires content")
        spans = payload.get("spans")
        for target_id in targets:
            node = _require_node(document, target_id)
            text = node.get("text")
            if node.get("kind") != "TEXT" or not isinstance(text, dict):
                raise OperationError(f"SET_TEXT target must be TEXT: {target_id}")
            text["content"] = content
            if spans is not None:
                if not isinstance(spans, list):
                    raise OperationError("SET_TEXT spans must be a list")
                text["spans"] = deepcopy(spans)
        return

    if op_type == "APPLY_STYLE":
        targets = _require_targets(operation)
        style_id = payload.get("style_id")
        mode = payload.get("mode", "APPEND")
        if not isinstance(style_id, str) or mode not in {"APPEND", "REPLACE"}:
            raise OperationError("APPLY_STYLE requires style_id and APPEND/REPLACE mode")
        styles = document.get("resources", {}).get("styles", {})
        if not isinstance(styles, dict) or style_id not in styles:
            raise OperationError(f"style resource does not exist: {style_id}")
        for target_id in targets:
            node = _require_node(document, target_id)
            refs = node.get("style_refs")
            if not isinstance(refs, list):
                raise OperationError(f"node {target_id} style_refs must be a list")
            if mode == "REPLACE":
                node["style_refs"] = [style_id]
            elif style_id not in refs:
                refs.append(style_id)
        return

    raise OperationError(f"unsupported primitive operation type: {op_type!r}")


def _validate_expected_version(operation: dict[str, Any], current_version: int) -> None:
    expected = operation.get("expected_document_version")
    if expected != current_version:
        raise DocumentVersionConflict(
            f"expected document version {expected!r}, current version is {current_version}"
        )


def _apply_without_version_increment(
    document: dict[str, Any],
    operation: dict[str, Any],
    current_version: int,
) -> None:
    _validate_expected_version(operation, current_version)
    if operation.get("type") != "BATCH":
        _apply_primitive(document, operation)
        return

    _require_targets(operation, count=0)
    payload = _require_payload(operation)
    if payload.get("atomic") is not True:
        raise OperationError("BATCH must declare atomic=true")
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise OperationError("BATCH requires one or more child operations")
    for child in operations:
        if not isinstance(child, dict):
            raise OperationError("BATCH child operation must be an object")
        _apply_without_version_increment(document, child, current_version)


def apply_operation(
    document: dict[str, Any],
    operation: dict[str, Any],
    *,
    current_version: int,
) -> AppliedOperation:
    """Apply one operation or atomic batch to a deep copy.

    The caller's document is never mutated. Any exception discards the working copy.
    Exactly one document version is consumed for a successful primitive or BATCH.
    """
    if current_version < 0:
        raise OperationError("current_version cannot be negative")
    validate_document(document)
    before_hash = content_hash(document)
    working = deepcopy(document)
    _apply_without_version_increment(working, operation, current_version)
    validate_document(working)
    after_hash = content_hash(working)
    return AppliedOperation(
        document=working,
        document_version=current_version + 1,
        before_hash=before_hash,
        after_hash=after_hash,
    )
