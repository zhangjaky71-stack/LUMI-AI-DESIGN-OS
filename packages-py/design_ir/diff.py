from __future__ import annotations

from .canonical import canonical_stringify
from .models import DesignDocument

GEOMETRY_KEYS = {"transform", "bounds", "x", "y", "width", "height", "rotation_deg"}
TEXT_KEYS = {"content", "spans"}
ASSET_KEYS = {"asset_id", "source_artifact_version_id"}
CONSTRAINT_KEYS = {"constraint_refs"}


def compute_semantic_diff(before: DesignDocument, after: DesignDocument) -> dict[str, list[str]]:
    before_nodes = before["nodes"]
    after_nodes = after["nodes"]
    before_ids = set(before_nodes)
    after_ids = set(after_nodes)
    properties: set[str] = set()
    text: set[str] = set()
    geometry: set[str] = set()
    assets: set[str] = set()
    constraints: set[str] = set()

    for node_id in before_ids & after_ids:
        left = before_nodes[node_id]
        right = after_nodes[node_id]
        for key in set(left) | set(right):
            if canonical_stringify(left.get(key)) == canonical_stringify(right.get(key)):
                continue
            if key in TEXT_KEYS:
                text.add(node_id)
            elif key in GEOMETRY_KEYS:
                geometry.add(node_id)
            elif key in ASSET_KEYS:
                assets.add(node_id)
            elif key in CONSTRAINT_KEYS:
                constraints.add(node_id)
            else:
                properties.add(f"{node_id}:{key}")
    return {
        "nodes_added": sorted(after_ids - before_ids),
        "nodes_removed": sorted(before_ids - after_ids),
        "properties_changed": sorted(properties),
        "text_changed": sorted(text),
        "geometry_changed": sorted(geometry),
        "asset_replaced": sorted(assets),
        "constraints_changed": sorted(constraints),
    }
