from __future__ import annotations

from typing import Any


class Node38SemanticDiffAdapter:
    """Thin adapter over the NODE-38 Python mirror.

    Import is intentionally lazy so Artifact Engine storage/lineage paths do not
    require Design IR unless a structured design comparison is requested.
    """

    def compare(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        from design_ir import compute_semantic_diff, parse_document

        before = parse_document(left)
        after = parse_document(right)
        diff = compute_semantic_diff(before, after)
        if hasattr(diff, "model_dump"):
            return diff.model_dump(mode="json")
        if isinstance(diff, dict):
            return diff
        return {
            key: value
            for key, value in vars(diff).items()
            if not key.startswith("_")
        }
