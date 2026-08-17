from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def project_operation(
    document: Mapping[str, Any], operation: Mapping[str, Any]
) -> dict[str, Any]:
    candidate = deepcopy(dict(document))
    nodes = candidate.setdefault("nodes", {})
    op_type = operation.get("type")
    targets = [str(value) for value in operation.get("target_ids", ())]
    payload = operation.get("payload", {})
    if not isinstance(payload, Mapping):
        return candidate
    if op_type == "CREATE_NODE":
        raw = payload.get("node")
        if isinstance(raw, Mapping):
            node = deepcopy(dict(raw))
            node_id = node.get("id")
            parent_id = node.get("parent_id")
            if isinstance(node_id, str):
                nodes[node_id] = node
                parent = nodes.get(parent_id)
                if isinstance(parent, dict):
                    children = list(parent.get("children", ()))
                    index = payload.get("index")
                    position = (
                        len(children)
                        if not isinstance(index, int)
                        else max(0, min(index, len(children)))
                    )
                    children.insert(position, node_id)
                    parent["children"] = children
        return candidate
    if op_type == "DELETE_NODE":
        for node_id in targets:
            node = nodes.get(node_id)
            if not isinstance(node, Mapping):
                continue
            parent = nodes.get(node.get("parent_id"))
            if isinstance(parent, dict):
                parent["children"] = [
                    value for value in parent.get("children", ()) if value != node_id
                ]
            stack = [node_id]
            while stack:
                current = stack.pop()
                child = nodes.pop(current, None)
                if isinstance(child, Mapping):
                    stack.extend(str(value) for value in child.get("children", ()))
        return candidate
    for node_id in targets:
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            continue
        if op_type == "SET_PROPERTY":
            prop = payload.get("property")
            if isinstance(prop, str):
                node[prop] = deepcopy(payload.get("value"))
        elif op_type in {"MOVE_NODE", "RESIZE_NODE", "ROTATE_NODE"}:
            transform = dict(node.get("transform") or {})
            if op_type == "MOVE_NODE":
                transform["x"] = payload.get("x")
                transform["y"] = payload.get("y")
            elif op_type == "RESIZE_NODE":
                transform["width"] = payload.get("width")
                transform["height"] = payload.get("height")
            else:
                transform["rotation_deg"] = payload.get("rotation_deg")
            node["transform"] = transform
        elif op_type == "REPARENT_NODE":
            old_parent = nodes.get(node.get("parent_id"))
            if isinstance(old_parent, dict):
                old_parent["children"] = [
                    value
                    for value in old_parent.get("children", ())
                    if value != node_id
                ]
            new_parent_id = payload.get("parent_id")
            node["parent_id"] = new_parent_id
            new_parent = nodes.get(new_parent_id)
            if isinstance(new_parent, dict):
                children = [value for value in new_parent.get("children", ()) if value != node_id]
                index = payload.get("index")
                position = (
                    len(children)
                    if not isinstance(index, int)
                    else max(0, min(index, len(children)))
                )
                children.insert(position, node_id)
                new_parent["children"] = children
        elif op_type == "REPLACE_ASSET":
            node["asset_id"] = payload.get("asset_id")
        elif op_type == "SET_TEXT":
            node["content"] = payload.get("content")
        elif op_type == "APPLY_STYLE":
            node["style_refs"] = deepcopy(payload.get("style_refs", ()))
    return candidate
