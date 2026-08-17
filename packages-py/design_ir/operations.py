from __future__ import annotations

from copy import deepcopy
from typing import Any

from .diff import compute_semantic_diff
from .models import (
    ConstraintPreflight,
    DesignDocument,
    DesignOperation,
    IrIssue,
    IrRuntimeError,
    OperationExecution,
)
from .validate import parse_document, validate_document, validate_operation


def _document_version(document: DesignDocument) -> int:
    value = document.get("metadata", {}).get("document_version", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _applied_ids(document: DesignDocument) -> list[str]:
    value = document.get("metadata", {}).get("applied_operation_ids", [])
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return []


def _fail(
    code: str,
    message: str,
    operation: DesignOperation,
    node_ids: tuple[str, ...] = (),
    pointer: str | None = None,
) -> None:
    raise IrRuntimeError(
        IrIssue(
            code,
            message,
            pointer=pointer,
            node_ids=node_ids,
            operation_id=operation.get("operation_id"),
        )
    )


def _targets(document: DesignDocument, operation: DesignOperation) -> list[dict[str, Any]]:
    ids = operation.get("target_ids", [])
    if not ids:
        _fail("IR_OPERATION_INVALID", "operation requires target_ids", operation)
    result: list[dict[str, Any]] = []
    for node_id in ids:
        node = document["nodes"].get(node_id)
        if not isinstance(node, dict):
            _fail("IR_TARGET_NOT_FOUND", f"target {node_id} not found", operation, (str(node_id),))
        result.append(node)
    return result


def _set_node(document: DesignDocument, node: dict[str, Any]) -> DesignDocument:
    document["nodes"][node["id"]] = deepcopy(node)
    return document


def _remove_from_parent(
    document: DesignDocument,
    node: dict[str, Any],
    operation: DesignOperation,
) -> DesignDocument:
    parent_id = node.get("parent_id")
    if parent_id is None:
        return document
    parent = document["nodes"].get(parent_id)
    if not isinstance(parent, dict):
        _fail("IR_REFERENCE_MISSING", f"parent {parent_id} not found", operation, (node["id"],))
    parent["children"] = [item for item in parent.get("children", []) if item != node["id"]]
    return document


def _insert_parent(
    document: DesignDocument,
    node_id: str,
    parent_id: str,
    index: int | None,
    operation: DesignOperation,
) -> DesignDocument:
    parent = document["nodes"].get(parent_id)
    if not isinstance(parent, dict):
        _fail("IR_REFERENCE_MISSING", f"parent {parent_id} not found", operation, (parent_id,))
    children = [item for item in parent.get("children", []) if item != node_id]
    position = len(children) if index is None else max(0, min(index, len(children)))
    children.insert(position, node_id)
    parent["children"] = children
    return document


def _subtree(document: DesignDocument, node_id: str) -> set[str]:
    result: set[str] = set()

    def walk(current: str) -> None:
        if current in result:
            return
        result.add(current)
        node = document["nodes"].get(current)
        if isinstance(node, dict):
            for child in node.get("children", []):
                if isinstance(child, str):
                    walk(child)

    walk(node_id)
    return result


def _single(document: DesignDocument, operation: DesignOperation) -> DesignDocument:
    validate_operation(operation)
    op_type = operation["type"]
    payload = operation["payload"]

    if op_type == "CREATE_NODE":
        node = payload.get("node")
        if not isinstance(node, dict):
            _fail("IR_OPERATION_INVALID", "CREATE_NODE requires payload.node", operation)
        node = deepcopy(node)
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            _fail("IR_OPERATION_INVALID", "created node requires id", operation)
        if node_id in document["nodes"]:
            _fail("IR_OPERATION_INVALID", f"node {node_id} exists", operation, (node_id,))
        parent_id = node.get("parent_id")
        if not isinstance(parent_id, str) or node.get("kind") == "DOCUMENT_ROOT":
            _fail("IR_OPERATION_INVALID", "cannot create a second root", operation, (node_id,))
        next_doc = document
        node["children"] = list(node.get("children", []))
        next_doc["nodes"][node_id] = node
        index = payload.get("index")
        return _insert_parent(
            next_doc,
            node_id,
            parent_id,
            index if isinstance(index, int) else None,
            operation,
        )

    if op_type == "DELETE_NODE":
        next_doc = document
        for node in _targets(next_doc, operation):
            node_id = node["id"]
            if node_id == next_doc["root_id"]:
                _fail("IR_OPERATION_INVALID", "cannot delete root", operation, (node_id,))
            remove_ids = _subtree(next_doc, node_id)
            next_doc = _remove_from_parent(next_doc, node, operation)
            next_doc["nodes"] = {
                key: value for key, value in next_doc["nodes"].items() if key not in remove_ids
            }
        return next_doc

    if op_type == "SET_PROPERTY":
        prop = payload.get("property")
        if (
            not isinstance(prop, str)
            or not prop
            or "." in prop
            or prop in {"id", "parent_id", "children", "kind"}
        ):
            _fail("IR_OPERATION_INVALID", "SET_PROPERTY property is invalid", operation)
        next_doc = document
        for node in _targets(next_doc, operation):
            updated = deepcopy(node)
            updated[prop] = deepcopy(payload.get("value"))
            next_doc = _set_node(next_doc, updated)
        return next_doc

    if op_type in {"MOVE_NODE", "RESIZE_NODE", "ROTATE_NODE"}:
        next_doc = document
        for node in _targets(next_doc, operation):
            updated = deepcopy(node)
            transform = deepcopy(updated.get("transform", {}))
            if op_type == "MOVE_NODE":
                x, y = payload.get("x"), payload.get("y")
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    _fail("IR_OPERATION_INVALID", "MOVE_NODE requires x/y", operation)
                transform["x"], transform["y"] = x, y
            elif op_type == "RESIZE_NODE":
                width, height = payload.get("width"), payload.get("height")
                if (
                    not isinstance(width, (int, float))
                    or not isinstance(height, (int, float))
                    or width < 0
                    or height < 0
                ):
                    _fail(
                        "IR_OPERATION_INVALID",
                        "RESIZE_NODE requires non-negative width/height",
                        operation,
                    )
                transform["width"], transform["height"] = width, height
            else:
                rotation = payload.get("rotation_deg")
                if not isinstance(rotation, (int, float)):
                    _fail("IR_OPERATION_INVALID", "ROTATE_NODE requires rotation_deg", operation)
                transform["rotation_deg"] = rotation
            updated["transform"] = transform
            next_doc = _set_node(next_doc, updated)
        return next_doc

    if op_type == "REORDER_NODE":
        node = _targets(document, operation)[0]
        parent_id = node.get("parent_id")
        index = payload.get("index")
        if parent_id is None or not isinstance(index, int):
            _fail("IR_OPERATION_INVALID", "REORDER_NODE requires integer index", operation)
        return _insert_parent(document, node["id"], parent_id, index, operation)

    if op_type == "REPARENT_NODE":
        node = _targets(document, operation)[0]
        parent_id = payload.get("parent_id")
        if not isinstance(parent_id, str) or not parent_id:
            _fail("IR_OPERATION_INVALID", "REPARENT_NODE requires parent_id", operation)
        if parent_id in _subtree(document, node["id"]):
            _fail(
                "IR_GRAPH_CYCLE",
                f"cannot reparent {node['id']} into its subtree",
                operation,
                (node["id"], parent_id),
            )
        next_doc = _remove_from_parent(document, node, operation)
        updated = deepcopy(node)
        updated["parent_id"] = parent_id
        next_doc = _set_node(next_doc, updated)
        index = payload.get("index")
        return _insert_parent(
            next_doc,
            node["id"],
            parent_id,
            index if isinstance(index, int) else None,
            operation,
        )

    if op_type == "REPLACE_ASSET":
        asset_id = payload.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id:
            _fail("IR_OPERATION_INVALID", "REPLACE_ASSET requires asset_id", operation)
        next_doc = document
        for node in _targets(next_doc, operation):
            updated = deepcopy(node)
            updated["asset_id"] = asset_id
            next_doc = _set_node(next_doc, updated)
        return next_doc

    if op_type == "SET_TEXT":
        content = payload.get("content")
        if not isinstance(content, str):
            _fail("IR_OPERATION_INVALID", "SET_TEXT requires content", operation)
        next_doc = document
        for node in _targets(next_doc, operation):
            if node.get("kind") != "TEXT":
                _fail(
                    "IR_OPERATION_INVALID",
                    "SET_TEXT target must be TEXT",
                    operation,
                    (node["id"],),
                )
            updated = deepcopy(node)
            updated["content"] = content
            next_doc = _set_node(next_doc, updated)
        return next_doc

    if op_type == "APPLY_STYLE":
        refs = payload.get("style_refs")
        if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
            _fail("IR_OPERATION_INVALID", "APPLY_STYLE requires style_refs[]", operation)
        next_doc = document
        for node in _targets(next_doc, operation):
            updated = deepcopy(node)
            updated["style_refs"] = list(refs)
            next_doc = _set_node(next_doc, updated)
        return next_doc

    if op_type == "BATCH":
        _fail("IR_OPERATION_INVALID", "nested BATCH must be handled by apply_operation", operation)
    _fail("IR_OPERATION_INVALID", f"unsupported operation {op_type}", operation)
    raise AssertionError("unreachable")


def apply_operation(
    document: DesignDocument,
    operation: DesignOperation,
    preflight: ConstraintPreflight | None = None,
) -> OperationExecution:
    before = parse_document(document)
    validate_operation(operation)
    current_version = _document_version(before)
    if operation["expected_document_version"] != current_version:
        _fail(
            "IR_VERSION_CONFLICT",
            f"expected version {operation['expected_document_version']}, current {current_version}",
            operation,
        )

    if operation["type"] == "BATCH":
        raw = operation["payload"].get("operations")
        if not isinstance(raw, list):
            _fail("IR_OPERATION_INVALID", "BATCH requires operations[]", operation)
        operations = deepcopy(raw)
        ids = [operation["operation_id"]] + [
            item.get("operation_id", "") for item in operations if isinstance(item, dict)
        ]
    else:
        operations = [operation]
        ids = [operation["operation_id"]]

    current_ids = set(_applied_ids(before))
    seen: set[str] = set()
    for op_id in ids:
        if not isinstance(op_id, str) or not op_id or op_id in current_ids or op_id in seen:
            _fail("IR_OPERATION_INVALID", f"duplicate operation_id {op_id}", operation)
        seen.add(op_id)

    working = deepcopy(before)
    try:
        for child in operations:
            if not isinstance(child, dict):
                _fail("IR_OPERATION_INVALID", "batch child must be an operation object", operation)
            if child.get("type") == "BATCH":
                _fail("IR_OPERATION_INVALID", "nested BATCH is forbidden", child)
            validate_operation(child)
            if child["expected_document_version"] != current_version:
                _fail(
                    "IR_VERSION_CONFLICT",
                    f"child {child['operation_id']} expected "
                    f"{child['expected_document_version']}, current {current_version}",
                    child,
                )
            if preflight is not None:
                issues = preflight(working, child)
                if issues:
                    raise IrRuntimeError(issues[0])
            working = _single(working, child)
        issues = validate_document(working)
        if issues:
            raise IrRuntimeError(issues[0])
    except IrRuntimeError as exc:
        if operation["type"] == "BATCH" and exc.code != "IR_VERSION_CONFLICT":
            raise IrRuntimeError(
                IrIssue(
                    "IR_BATCH_FAILED",
                    str(exc),
                    pointer=exc.pointer,
                    node_ids=exc.node_ids,
                    operation_id=operation["operation_id"],
                )
            ) from exc
        raise

    next_version = current_version + 1
    working.setdefault("metadata", {})["document_version"] = next_version
    working["metadata"]["applied_operation_ids"] = _applied_ids(before) + ids
    final = parse_document(working)
    return OperationExecution(
        document=final,
        previous_version=current_version,
        document_version=next_version,
        applied_operation_ids=tuple(ids),
        diff=compute_semantic_diff(before, final),
    )


def apply_batch(
    document: DesignDocument,
    operations: list[DesignOperation],
    expected_document_version: int,
    operation_id: str | None = None,
    preflight: ConstraintPreflight | None = None,
) -> OperationExecution:
    batch_id = operation_id or "batch:" + "+".join(item["operation_id"] for item in operations)
    return apply_operation(
        document,
        {
            "operation_id": batch_id,
            "type": "BATCH",
            "target_ids": [],
            "expected_document_version": expected_document_version,
            "payload": {"operations": deepcopy(operations)},
        },
        preflight,
    )
