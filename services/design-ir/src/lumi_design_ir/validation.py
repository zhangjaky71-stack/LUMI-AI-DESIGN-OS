from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import ResourceReferenceError, StructuralValidationError
from .unicode_ranges import validate_codepoint_spans


NODE_KINDS = frozenset(
    {
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
)


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StructuralValidationError(f"{label} must be an object")
    return value


def _walk_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise StructuralValidationError(f"non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _walk_finite(item, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _walk_finite(item, f"{path}[{index}]")


def _resource_ids(resources: Mapping[str, Any], bucket: str) -> set[str]:
    value = resources.get(bucket, {})
    mapping = _require_mapping(value, f"resources.{bucket}")
    return {str(key) for key in mapping}


def validate_document(document: Mapping[str, Any]) -> None:
    if document.get("schema_version") != "1.0":
        raise StructuralValidationError("schema_version must be 1.0")
    if document.get("unit") != "px":
        raise StructuralValidationError("V1 unit must be px")

    nodes = _require_mapping(document.get("nodes"), "nodes")
    resources = _require_mapping(document.get("resources"), "resources")
    root_id = document.get("root_id")
    if not isinstance(root_id, str) or root_id not in nodes:
        raise StructuralValidationError("root_id must reference an existing node")

    root = _require_mapping(nodes[root_id], f"nodes.{root_id}")
    if root.get("kind") != "DOCUMENT_ROOT":
        raise StructuralValidationError("root node must use DOCUMENT_ROOT kind")
    if root.get("parent_id") is not None:
        raise StructuralValidationError("root node parent_id must be null")

    _walk_finite(document)

    parents: dict[str, str | None] = {}
    children_map: dict[str, tuple[str, ...]] = {}
    for node_key, raw_node in nodes.items():
        if not isinstance(node_key, str):
            raise StructuralValidationError("node map keys must be strings")
        node = _require_mapping(raw_node, f"nodes.{node_key}")
        if node.get("id") != node_key:
            raise StructuralValidationError(f"node map key/id mismatch for {node_key}")
        kind = node.get("kind")
        if kind not in NODE_KINDS:
            raise StructuralValidationError(f"unsupported node kind {kind!r} at {node_key}")
        parent_id = node.get("parent_id")
        if parent_id is not None and not isinstance(parent_id, str):
            raise StructuralValidationError(f"parent_id must be string/null at {node_key}")
        raw_children = node.get("children")
        if not isinstance(raw_children, list) or not all(isinstance(child, str) for child in raw_children):
            raise StructuralValidationError(f"children must be a string list at {node_key}")
        if len(raw_children) != len(set(raw_children)):
            raise StructuralValidationError(f"duplicate child id at {node_key}")
        parents[node_key] = parent_id
        children_map[node_key] = tuple(raw_children)

        if kind == "TEXT":
            text = _require_mapping(node.get("text"), f"nodes.{node_key}.text")
            content = text.get("content")
            spans = text.get("spans", [])
            if not isinstance(content, str) or not isinstance(spans, list):
                raise StructuralValidationError(f"invalid text payload at {node_key}")
            validate_codepoint_spans(content, spans)

    for node_id, parent_id in parents.items():
        if node_id == root_id:
            continue
        if parent_id is None or parent_id not in nodes:
            raise StructuralValidationError(f"node {node_id} has missing parent {parent_id!r}")
        if node_id not in children_map[parent_id]:
            raise StructuralValidationError(f"parent {parent_id} does not list child {node_id}")

    for parent_id, child_ids in children_map.items():
        for child_id in child_ids:
            if child_id not in nodes:
                raise StructuralValidationError(f"parent {parent_id} references missing child {child_id}")
            if parents[child_id] != parent_id:
                raise StructuralValidationError(
                    f"child {child_id} parent_id does not match parent {parent_id}"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise StructuralValidationError(f"cycle detected at node {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child_id in children_map[node_id]:
            visit(child_id)
        visiting.remove(node_id)
        visited.add(node_id)

    visit(root_id)
    if visited != set(nodes):
        unreachable = sorted(set(nodes) - visited)
        raise StructuralValidationError(f"unreachable nodes: {unreachable}")

    asset_ids = _resource_ids(resources, "assets")
    font_ids = _resource_ids(resources, "fonts")
    style_ids = _resource_ids(resources, "styles")

    for node_id, raw_node in nodes.items():
        node = _require_mapping(raw_node, f"nodes.{node_id}")
        for style_id in node.get("style_refs", []):
            if style_id not in style_ids:
                raise ResourceReferenceError(f"node {node_id} references missing style {style_id}")

        kind = node.get("kind")
        if kind == "IMAGE":
            image = _require_mapping(node.get("image"), f"nodes.{node_id}.image")
            asset_id = image.get("asset_id")
            if asset_id not in asset_ids:
                raise ResourceReferenceError(f"image node {node_id} references missing asset {asset_id}")
            mask_id = image.get("mask_id")
            if mask_id is not None:
                mask = nodes.get(mask_id)
                if not isinstance(mask, Mapping) or mask.get("kind") != "MASK":
                    raise ResourceReferenceError(f"image node {node_id} references invalid mask {mask_id}")
        elif kind == "VIDEO":
            video = _require_mapping(node.get("video"), f"nodes.{node_id}.video")
            for field in ("asset_id", "poster_asset_id"):
                asset_id = video.get(field)
                if asset_id is not None and asset_id not in asset_ids:
                    raise ResourceReferenceError(
                        f"video node {node_id} references missing asset {asset_id} in {field}"
                    )
        elif kind == "TEXT":
            text = _require_mapping(node.get("text"), f"nodes.{node_id}.text")
            font_asset_id = text.get("font_asset_id")
            if font_asset_id is not None and font_asset_id not in font_ids:
                raise ResourceReferenceError(
                    f"text node {node_id} references missing font {font_asset_id}"
                )
        elif kind == "INSTANCE":
            instance = _require_mapping(node.get("instance"), f"nodes.{node_id}.instance")
            component_id = instance.get("component_id")
            component = nodes.get(component_id)
            if not isinstance(component, Mapping) or component.get("kind") != "COMPONENT":
                raise ResourceReferenceError(
                    f"instance node {node_id} references invalid component {component_id}"
                )
