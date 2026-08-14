from __future__ import annotations

import base64
from pathlib import Path

import pytest

from lumi_domain.constraint_media import OpenCvProtectedRegionComparator, ProtectedRegionEvaluator
from lumi_domain.constraint_validator import (
    OpenCvQrDecoder,
    QrScannabilityEvaluator,
    ResolutionEvaluator,
    guarded_execute,
    postflight_validate,
    resolve_constraints,
)

FIXTURE_PATH = Path("fixtures/constraints/qr-valid.png.base64")
QR_PAYLOAD = "https://lumi.example/qr"


def _document() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "document_id": "doc-1",
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
                "children": ["qr", "headline"],
                "transform": {"x": 0, "y": 0, "width": 750, "height": 1624},
            },
            "qr": {
                "id": "qr",
                "kind": "IMAGE",
                "parent_id": "frame",
                "children": [],
                "asset_id": "qr-asset",
                "transform": {"x": 100, "y": 100, "width": 180, "height": 180},
            },
            "headline": {
                "id": "headline",
                "kind": "TEXT",
                "parent_id": "frame",
                "children": [],
                "content": "Hello",
                "transform": {"x": 100, "y": 400, "width": 300, "height": 80},
            },
        },
        "resources": {},
        "metadata": {"document_version": 12},
    }


def _operation(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "operation_id": "op-1",
        "type": "MOVE_NODE",
        "target_ids": ["qr"],
        "expected_document_version": 12,
        "payload": {"dx": 20, "dy": 0},
    }
    value.update(overrides)
    return value


def _constraint(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "c-lock",
        "type": "LOCK_POSITION",
        "scope": {"node_ids": ["qr"]},
        "severity": "HARD",
        "source": "USER_EXPLICIT",
        "priority": 1000,
        "parameters": {},
        "active": True,
        "document_version": 12,
    }
    value.update(overrides)
    return value


def _qr_bytes() -> bytes:
    return base64.b64decode(FIXTURE_PATH.read_text().strip())


def test_hard_position_lock_denies_without_candidate() -> None:
    document = _document()
    result = guarded_execute(document, [_operation()], [_constraint()])
    assert result["preflight"]["decision"] == "DENY"
    assert "execution" not in result
    assert result["preflight"]["violations"][0]["reason_code"] == "CONSTRAINT_POSITION_CHANGED"
    assert document["metadata"] == {"document_version": 12}


def test_soft_position_lock_allows_with_warning() -> None:
    result = guarded_execute(document=_document(), operations=[_operation()], constraints=[_constraint(severity="SOFT")])
    assert result["preflight"]["decision"] == "ALLOW_WITH_WARNINGS"
    assert result["execution"]["ok"] is True


def test_batch_is_atomic_when_one_child_breaks_hard_lock() -> None:
    batch = _operation(
        operation_id="batch",
        type="BATCH",
        target_ids=[],
        payload={
            "operations": [
                _operation(operation_id="move"),
                _operation(
                    operation_id="text",
                    type="SET_TEXT",
                    target_ids=["headline"],
                    payload={"content": "Changed"},
                ),
            ]
        },
    )
    result = guarded_execute(_document(), [batch], [_constraint()])
    assert result["preflight"]["decision"] == "DENY"
    assert "execution" not in result


def test_stale_hard_constraint_fails_closed() -> None:
    result = guarded_execute(_document(), [_operation()], [_constraint(document_version=11)])
    assert result["preflight"]["decision"] == "DENY"
    assert result["preflight"]["violations"][0]["reason_code"] == "STALE_CONSTRAINT_SNAPSHOT"


def test_override_is_document_and_version_scoped() -> None:
    override = {
        "token_id": "override-1",
        "constraint_id": "c-lock",
        "document_id": "doc-1",
        "document_version": 12,
        "actor": "user-1",
        "reason": "Approved one-time move",
        "one_time": True,
    }
    result = guarded_execute(_document(), [_operation()], [_constraint()], overrides=[override])
    assert result["preflight"]["decision"] == "ALLOW"
    assert result["execution"]["ok"] is True


def test_equal_precedence_incompatible_rules_surface_conflict() -> None:
    resolved = resolve_constraints(
        _document(),
        [
            _constraint(id="a", type="MIN_MARGIN", parameters={"container_id": "frame", "min_px": 24}),
            _constraint(id="b", type="MIN_MARGIN", parameters={"container_id": "frame", "min_px": 48}),
        ],
    )
    assert len(resolved["conflicts"]) == 1
    assert resolved["constraints"] == []


def test_real_opencv_qr_decoder_preserves_payload() -> None:
    pytest.importorskip("cv2")
    result = OpenCvQrDecoder().decode(_qr_bytes())
    assert result.detected is True
    assert result.payload == QR_PAYLOAD


def test_real_qr_postflight_detects_payload_mismatch() -> None:
    pytest.importorskip("cv2")
    evaluator = QrScannabilityEvaluator(OpenCvQrDecoder(), lambda _ref: _qr_bytes())
    constraint = _constraint(
        id="qr-check",
        type="REQUIRE_SCANNABILITY",
        parameters={"payload": "https://wrong.example/qr"},
    )
    context = {
        "document": _document(),
        "constraints": [constraint],
        "before_ref": {"artifact_id": "a", "version": "1", "bytes_ref": "before"},
        "after_ref": {"artifact_id": "a", "version": "2", "bytes_ref": "after"},
    }
    result = postflight_validate(context, [evaluator])
    assert result["decision"] == "FAIL"
    assert result["violations"][0]["reason_code"] == "QR_PAYLOAD_CHANGED"


def test_hard_validator_unavailable_never_passes() -> None:
    constraint = _constraint(id="qr-check", type="REQUIRE_SCANNABILITY")
    context = {
        "document": _document(),
        "constraints": [constraint],
        "before_ref": {"artifact_id": "a", "version": "1"},
        "after_ref": {"artifact_id": "a", "version": "2"},
    }
    result = postflight_validate(context, [])
    assert result["decision"] == "FAIL"
    assert result["violations"][0]["reason_code"] == "VALIDATION_UNAVAILABLE"


def test_resolution_rule_is_deterministic() -> None:
    constraint = _constraint(
        id="resolution",
        type="REQUIRE_RESOLUTION",
        parameters={"min_width": 1000, "min_height": 2000},
    )
    context = {
        "document": _document(),
        "constraints": [constraint],
        "before_ref": {"artifact_id": "a", "version": "1", "width": 750, "height": 1624},
        "after_ref": {"artifact_id": "a", "version": "2", "width": 750, "height": 1624},
    }
    result = postflight_validate(context, [ResolutionEvaluator()])
    assert result["decision"] == "FAIL"
    assert result["violations"][0]["reason_code"] == "RESOLUTION_TOO_LOW"


def test_protected_region_tolerates_jpeg_compression_but_rejects_content_change() -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    original = _qr_bytes()
    image = cv2.imdecode(np.frombuffer(original, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    ok, encoded_jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    changed = image.copy()
    cv2.rectangle(changed, (120, 120), (220, 220), (0, 0, 255), -1)
    ok, encoded_changed = cv2.imencode(".png", changed)
    assert ok
    blobs = {
        "original": original,
        "compressed": encoded_jpeg.tobytes(),
        "changed": encoded_changed.tobytes(),
    }
    comparator = OpenCvProtectedRegionComparator(lambda ref: blobs[ref])
    evaluator = ProtectedRegionEvaluator(comparator)
    constraint = _constraint(
        id="region",
        type="PROTECT_REGION",
        scope={"region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}},
        parameters={"min_ssim": 0.985, "max_edge_difference": 0.04, "max_color_delta_e": 3.0},
    )
    compressed_context = {
        "document": _document(),
        "constraints": [constraint],
        "before_ref": {"artifact_id": "a", "version": "1", "bytes_ref": "original"},
        "after_ref": {"artifact_id": "a", "version": "2", "bytes_ref": "compressed"},
    }
    assert postflight_validate(compressed_context, [evaluator])["decision"] == "PASS"
    changed_context = {
        **compressed_context,
        "after_ref": {"artifact_id": "a", "version": "3", "bytes_ref": "changed"},
    }
    result = postflight_validate(changed_context, [evaluator])
    assert result["decision"] == "FAIL"
    assert result["violations"][0]["reason_code"] == "PROTECTED_REGION_CHANGED"
