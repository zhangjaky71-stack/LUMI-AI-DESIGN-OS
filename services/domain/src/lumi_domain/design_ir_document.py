from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

SUPPORTED_KINDS = {
    "DOCUMENT_ROOT",
    "FRAME",
    "GROUP",
    "TEXT",
    "IMAGE",
    "SHAPE",
    "VECTOR_PATH",
    "VIDEO",
    "MASK",
    "GUIDE",
    "COMPONENT",
    "INSTANCE",
}


def _issue(
    issues: list[dict[str, str]],
    code: str,
    message: str,
    pointer: str,
    node_id: str | None = None,
) -> None:
    value = {"code": code, "message": message, "pointer": pointer}
    if node_id is not None:
        value["node_id"] = node_id
    issues.append(value)


def _finite_walk(value: Any, pointer: str, issues: list[dict[str, str]]) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _issue(issues, "IR_SCHEMA_INVALID", "Numeric values must be finite", pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _finite_walk(child, f"{pointer}/{index}", issues)
    elif isinstance(value, dict):
        for key, child in value.items():
            _finite_walk(child, f"{pointer}/{key}", issues)


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    schema_version = document.get("schema_version")
    if not isinstance(schema_version, str) or schema_version.split(".")[0] != "1":
        _issue(issues, "IR_VERSION_UNSUPPORTED", "Only Design IR major version 1 is supported", "/schema_version")
    nodes = document.get("nodes")
    if not isinstance(nodes, dict):
        _issue(issues, "IR_SCHEMA_INVALID", "nodes must be an object", "/nodes")
        nodes = {}
    root_id = document.get("root_id")
    if not isinstance(root_id, str) or root_id not in nodes:
        _issue(issues, "IR_REFERENCE_MISSING", "root_id must reference an existing node", "/root_id")

    for node_id, raw in nodes.items():
        pointer = f"/nodes/{node_id}"
        if not isinstance(raw, dict):
            _issue(issues, "IR_SCHEMA_INVALID", "node must be an object", pointer, str(node_id))
            continue
        if raw.get("id") != node_id:
            _issue(issues, "IR_SCHEMA_INVALID", "Node map key must equal node.id", f"{pointer}/id", str(node_id))
        kind = raw.get("kind")
        if not isinstance(kind, str) or (kind not in SUPPORTED_KINDS and not kind.startswith("custom:")):
            _issue(issues, "IR_SCHEMA_INVALID", f"Unsupported node kind {kind}", f"{pointer}/kind", str(node_id))
        parent_id = raw.get("parent_id")
        if parent_id is not None and parent_id not in nodes:
            _issue(issues, "IR_REFERENCE_MISSING", f"Parent {parent_id} does not exist", f"{pointer}/parent_id", str(node_id))
        children = raw.get("children")
        if not isinstance(children, list):
            _issue(issues, "IR_SCHEMA_INVALID", "children must be an array", f"{pointer}/children", str(node_id))
            continue
        for index, child_id in enumerate(children):
            child = nodes.get(child_id)
            if not isinstance(child, dict):
                _issue(issues, "IR_REFERENCE_MISSING", f"Child {child_id} does not exist", f"{pointer}/children/{index}", str(node_id))
            elif child.get("parent_id") != node_id:
                _issue(issues, "IR_SCHEMA_INVALID", f"Child {child_id} parent_id mismatch", f"{pointer}/children/{index}", str(node_id))

    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in visiting:
            _issue(issues, "IR_GRAPH_CYCLE", f"Cycle detected at {node_id}", f"/nodes/{node_id}", node_id)
            return
        if node_id in visited:
            return
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            return
        visiting.add(node_id)
        for child_id in node.get("children", []):
            if isinstance(child_id, str):
                walk(child_id)
        visiting.remove(node_id)
        visited.add(node_id)

    if isinstance(root_id, str):
        walk(root_id)
    _finite_walk(document, "", issues)
    return {"valid": not issues, "issues": issues}


def parse_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("IR_SCHEMA_INVALID: document must be an object")
    document = deepcopy(raw)
    for required in ("schema_version", "document_id", "root_id", "nodes", "resources", "metadata"):
        if required not in document:
            raise ValueError(f"IR_SCHEMA_INVALID: missing /{required}")
    result = validate_document(document)
    if not result["valid"]:
        first = result["issues"][0]
        raise ValueError(f"{first['code']}: {first['pointer']} {first['message']}")
    return document


def query_nodes(document: dict[str, Any], selector: dict[str, Any]) -> list[dict[str, Any]]:
    ids = set(selector["ids"]) if isinstance(selector.get("ids"), list) else None
    roles = set(selector["roles"]) if isinstance(selector.get("roles"), list) else None
    kinds = set(selector["kinds"]) if isinstance(selector.get("kinds"), list) else None
    result: list[dict[str, Any]] = []
    for node in document.get("nodes", {}).values():
        if not isinstance(node, dict):
            continue
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        if ids is not None and node.get("id") not in ids:
            continue
        if roles is not None and node.get("role") not in roles:
            continue
        if kinds is not None and node.get("kind") not in kinds:
            continue
        if "parent_id" in selector and node.get("parent_id") != selector["parent_id"]:
            continue
        if "locked" in selector and bool(node.get("locked")) != selector["locked"]:
            continue
        if "brand_binding" in selector and metadata.get("brand_binding") != selector["brand_binding"]:
            continue
        asset_binding = selector.get("asset_binding")
        if asset_binding is not None and node.get("asset_id") != asset_binding and metadata.get("asset_binding") != asset_binding:
            continue
        result.append(deepcopy(node))
    return result


def spatial_entries(document: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for node in document.get("nodes", {}).values():
        if not isinstance(node, dict) or not isinstance(node.get("transform"), dict):
            continue
        transform = node["transform"]
        values = [transform.get(key) for key in ("x", "y", "width", "height")]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            continue
        entries.append(
            {
                "node_id": node.get("id"),
                "bounds": {"x": values[0], "y": values[1], "width": values[2], "height": values[3]},
            }
        )
    return entries
