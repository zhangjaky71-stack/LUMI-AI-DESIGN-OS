from __future__ import annotations

from .models import DesignDocument


def _binding(node: dict, key: str) -> object:
    if key in node:
        return node[key]
    semantic = node.get("semantic")
    return semantic.get(key) if isinstance(semantic, dict) else None


def _descendant_of(document: DesignDocument, node: dict, ancestor_id: str) -> bool:
    current = node.get("parent_id")
    while current is not None:
        if current == ancestor_id:
            return True
        parent = document["nodes"].get(current)
        current = parent.get("parent_id") if isinstance(parent, dict) else None
    return False


def query_nodes(document: DesignDocument, selector: dict) -> list[dict]:
    node_id = selector.get("id")
    if node_id is not None:
        node = document["nodes"].get(node_id)
        return [node] if isinstance(node, dict) else []

    result: list[dict] = []
    for node in document["nodes"].values():
        if not isinstance(node, dict):
            continue
        if "role" in selector and node.get("role") != selector["role"]:
            continue
        if "kind" in selector and node.get("kind") != selector["kind"]:
            continue
        if "parent_id" in selector and node.get("parent_id") != selector["parent_id"]:
            continue
        if "locked" in selector and bool(node.get("locked")) != selector["locked"]:
            continue
        if "brand_binding" in selector:
            if _binding(node, "brand_binding") != selector["brand_binding"]:
                continue
        if "asset_binding" in selector and _binding(node, "asset_id") != selector["asset_binding"]:
            continue
        if "frame_id" in selector:
            frame_id = selector["frame_id"]
            if node.get("id") != frame_id and not _descendant_of(document, node, frame_id):
                continue
        result.append(node)
    return result
