from __future__ import annotations

from lumi_domain.constraint_quality import StructuredContrastEvaluator, contrast_ratio
from lumi_domain.constraint_validator import constraint_snapshot_hash, guarded_execute


def _document() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "document_id": "quality-doc",
        "unit": "px",
        "root_id": "root",
        "nodes": {
            "root": {
                "id": "root",
                "kind": "DOCUMENT_ROOT",
                "parent_id": None,
                "children": ["frame"],
            },
            "frame": {
                "id": "frame",
                "kind": "FRAME",
                "parent_id": "root",
                "children": ["logo"],
                "transform": {"x": 0, "y": 0, "width": 1000, "height": 1000},
            },
            "logo": {
                "id": "logo",
                "kind": "IMAGE",
                "parent_id": "frame",
                "children": [],
                "transform": {"x": 100, "y": 100, "width": 200, "height": 200},
            },
        },
        "resources": {},
        "metadata": {"document_version": 1},
    }


def _safe_area() -> dict[str, object]:
    return {
        "id": "safe",
        "type": "SAFE_AREA",
        "scope": {
            "node_ids": ["logo"],
            "frame_id": "frame",
            "region": {"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.9},
        },
        "severity": "HARD",
        "source": "APPROVED_BRAND_RULE",
        "priority": 500,
        "parameters": {},
        "active": True,
        "document_version": 1,
    }


def test_safe_area_uses_normalized_frame_coordinates() -> None:
    operation = {
        "operation_id": "move-logo",
        "type": "MOVE_NODE",
        "target_ids": ["logo"],
        "expected_document_version": 1,
        "payload": {"x": 10, "y": 10},
    }
    result = guarded_execute(_document(), [operation], [_safe_area()])
    assert result["preflight"]["decision"] == "DENY"
    assert result["preflight"]["violations"][0]["reason_code"] == "CONSTRAINT_OUTSIDE_SAFE_AREA"


def test_structured_contrast_profile_is_deterministic() -> None:
    assert contrast_ratio("#000000", "#ffffff") == 21.0
    constraint = {
        "id": "contrast",
        "type": "REQUIRE_CONTRAST",
        "scope": {"node_ids": ["logo"]},
        "severity": "HARD",
        "source": "PROJECT_RULE",
        "priority": 100,
        "parameters": {"foreground": "#777777", "background": "#ffffff", "min_ratio": 7},
        "active": True,
    }
    violations = StructuredContrastEvaluator().evaluate({}, constraint)
    assert violations[0]["reason_code"] == "CONTRAST_BELOW_PROFILE_THRESHOLD"


def test_constraint_snapshot_hash_is_stable() -> None:
    first = constraint_snapshot_hash(_document(), [_safe_area()])
    second = constraint_snapshot_hash(_document(), [_safe_area()])
    assert first == second
    assert len(first) == 64
