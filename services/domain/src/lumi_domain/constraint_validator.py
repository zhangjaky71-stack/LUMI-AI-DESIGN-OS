from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .design_ir_canonical import canonical_sha256
from .design_ir_runtime import execute_operations

JsonObject = dict[str, Any]

SOURCE_PRECEDENCE: dict[str, int] = {
    "SAFETY_SYSTEM": 700,
    "USER_EXPLICIT": 600,
    "APPROVED_BRAND_RULE": 500,
    "PROJECT_RULE": 400,
    "RECIPE_RULE": 300,
    "AGENT_INFERRED": 200,
    "STYLE_PREFERENCE": 100,
}

DEFAULT_TOLERANCE: dict[str, float] = {
    "position_px": 0.25,
    "size_px": 0.25,
    "rotation_deg": 0.05,
    "aspect_ratio": 0.001,
    "overlap_px": 0.25,
}

POSTFLIGHT_REQUIRED_TYPES = frozenset(
    {
        "PROTECT_REGION",
        "REQUIRE_SCANNABILITY",
        "LOCK_IDENTITY",
        "REQUIRE_IDENTITY_SCORE",
        "REQUIRE_BRAND_COMPLIANCE",
        "REQUIRE_CONTRAST",
        "REQUIRE_TEXT_READABILITY",
        "REQUIRE_RESOLUTION",
    }
)


@dataclass(frozen=True, slots=True)
class QrDecodeResult:
    detected: bool
    payload: str | None = None
    readable_at_target_size: bool | None = None
    quiet_zone_modules: float | None = None
    evidence_ref: str | None = None


class QrDecoder(Protocol):
    def decode(self, image_bytes: bytes) -> QrDecodeResult: ...


class PostflightEvaluator(Protocol):
    name: str
    supported_types: frozenset[str]

    def evaluate(
        self,
        context: Mapping[str, Any],
        constraint: Mapping[str, Any],
    ) -> list[JsonObject]: ...


class OpenCvQrDecoder:
    """Real QR decoder adapter. OpenCV is intentionally an optional runtime plugin."""

    def decode(self, image_bytes: bytes) -> QrDecodeResult:
        try:
            import cv2  # type: ignore[import-not-found]
            import numpy as np  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("OpenCV QR decoder is unavailable") from exc

        encoded = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            return QrDecodeResult(detected=False)
        detector = cv2.QRCodeDetector()
        payload, points, _ = detector.detectAndDecode(image)
        detected = points is not None and bool(payload)
        return QrDecodeResult(
            detected=detected,
            payload=payload or None,
            readable_at_target_size=detected,
        )


class QrScannabilityEvaluator:
    name = "qr-scannability"
    supported_types = frozenset({"REQUIRE_SCANNABILITY"})

    def __init__(self, decoder: QrDecoder, image_loader: Callable[[str], bytes]) -> None:
        self._decoder = decoder
        self._image_loader = image_loader

    def evaluate(
        self,
        context: Mapping[str, Any],
        constraint: Mapping[str, Any],
    ) -> list[JsonObject]:
        after_ref = context.get("after_ref", {})
        if not isinstance(after_ref, Mapping):
            raise RuntimeError("after_ref is required")
        bytes_ref = after_ref.get("bytes_ref")
        if not isinstance(bytes_ref, str) or not bytes_ref:
            raise RuntimeError("after_ref.bytes_ref is required for QR validation")

        decoded = self._decoder.decode(self._image_loader(bytes_ref))
        parameters = _parameters(constraint)
        expected_payload = parameters.get("payload")
        violations: list[JsonObject] = []
        if not decoded.detected or decoded.payload is None:
            return [
                _violation(
                    constraint,
                    self.name,
                    "QR_NOT_DECODABLE",
                    evidence_ref=decoded.evidence_ref,
                    repair_hint={"action": "restore_qr_or_increase_size"},
                )
            ]
        if isinstance(expected_payload, str) and decoded.payload != expected_payload:
            violations.append(
                _violation(
                    constraint,
                    self.name,
                    "QR_PAYLOAD_CHANGED",
                    expected=expected_payload,
                    actual=decoded.payload,
                    evidence_ref=decoded.evidence_ref,
                    repair_hint={"action": "restore_qr_payload"},
                )
            )
        if decoded.readable_at_target_size is False:
            violations.append(
                _violation(
                    constraint,
                    self.name,
                    "QR_UNREADABLE_AT_EXPORT_SIZE",
                    evidence_ref=decoded.evidence_ref,
                    repair_hint={"action": "increase_qr_export_size"},
                )
            )
        minimum_quiet = _number(parameters.get("min_quiet_zone_modules"), 4.0)
        if (
            decoded.quiet_zone_modules is not None
            and decoded.quiet_zone_modules < minimum_quiet
        ):
            warning = _violation(
                constraint,
                self.name,
                "QR_QUIET_ZONE_TOO_SMALL",
                expected=minimum_quiet,
                actual=decoded.quiet_zone_modules,
                evidence_ref=decoded.evidence_ref,
                repair_hint={"action": "increase_qr_quiet_zone"},
            )
            if warning["severity"] == "HARD":
                warning["severity"] = "SOFT"
            violations.append(warning)
        return violations


class ResolutionEvaluator:
    name = "resolution"
    supported_types = frozenset({"REQUIRE_RESOLUTION"})

    def evaluate(
        self,
        context: Mapping[str, Any],
        constraint: Mapping[str, Any],
    ) -> list[JsonObject]:
        after_ref = context.get("after_ref", {})
        after_ref = after_ref if isinstance(after_ref, Mapping) else {}
        width = _number(after_ref.get("width"))
        height = _number(after_ref.get("height"))
        parameters = _parameters(constraint)
        minimum_width = _number(parameters.get("min_width"))
        minimum_height = _number(parameters.get("min_height"))
        if width >= minimum_width and height >= minimum_height:
            return []
        return [
            _violation(
                constraint,
                self.name,
                "RESOLUTION_TOO_LOW",
                expected={"width": minimum_width, "height": minimum_height},
                actual={"width": width, "height": height},
                repair_hint={"action": "regenerate_or_upscale"},
            )
        ]


def _parameters(constraint: Mapping[str, Any]) -> Mapping[str, Any]:
    value = constraint.get("parameters", {})
    return value if isinstance(value, Mapping) else {}


def _scope(constraint: Mapping[str, Any]) -> Mapping[str, Any]:
    value = constraint.get("scope", {})
    return value if isinstance(value, Mapping) else {}


def _target_ids(constraint: Mapping[str, Any]) -> list[str]:
    values = _scope(constraint).get("node_ids", [])
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [value for value in values if isinstance(value, str)]


def _number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return fallback
    return float(value)


def _transform(node: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not node:
        return {}
    value = node.get("transform", {})
    return value if isinstance(value, Mapping) else {}


def _bounds(node: Mapping[str, Any] | None) -> JsonObject:
    value = _transform(node)
    return {
        "x": _number(value.get("x")),
        "y": _number(value.get("y")),
        "width": max(0.0, _number(value.get("width"))),
        "height": max(0.0, _number(value.get("height"))),
    }


def _close(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def _inside(
    inner: Mapping[str, Any],
    outer: Mapping[str, Any],
    margin: float,
    tolerance: float,
) -> bool:
    return (
        _number(inner.get("x")) + tolerance >= _number(outer.get("x")) + margin
        and _number(inner.get("y")) + tolerance >= _number(outer.get("y")) + margin
        and _number(inner.get("x")) + _number(inner.get("width")) - tolerance
        <= _number(outer.get("x")) + _number(outer.get("width")) - margin
        and _number(inner.get("y")) + _number(inner.get("height")) - tolerance
        <= _number(outer.get("y")) + _number(outer.get("height")) - margin
    )


def _intersects(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    tolerance: float,
) -> bool:
    overlap_x = min(
        _number(left.get("x")) + _number(left.get("width")),
        _number(right.get("x")) + _number(right.get("width")),
    ) - max(_number(left.get("x")), _number(right.get("x")))
    overlap_y = min(
        _number(left.get("y")) + _number(left.get("height")),
        _number(right.get("y")) + _number(right.get("height")),
    ) - max(_number(left.get("y")), _number(right.get("y")))
    return overlap_x > tolerance and overlap_y > tolerance


def _violation(
    constraint: Mapping[str, Any],
    validator: str,
    reason_code: str,
    *,
    target_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    repair_hint: Mapping[str, Any] | None = None,
    evidence_ref: str | None = None,
) -> JsonObject:
    value: JsonObject = {
        "constraint_id": str(constraint.get("id", "unknown")),
        "type": str(constraint.get("type", "unknown")),
        "severity": str(constraint.get("severity", "HARD")),
        "validator": validator,
        "reason_code": reason_code,
    }
    if target_id is not None:
        value["target_id"] = target_id
    if expected is not None:
        value["expected"] = deepcopy(expected)
    if actual is not None:
        value["actual"] = deepcopy(actual)
    if repair_hint is not None:
        value["repair_hint"] = dict(repair_hint)
    if evidence_ref is not None:
        value["raw_evidence_ref"] = evidence_ref
    return value


def _scope_key(constraint: Mapping[str, Any]) -> str:
    scope = _scope(constraint)
    return json.dumps(
        {
            "type": str(constraint.get("type")),
            "node_ids": sorted(_target_ids(constraint)),
            "frame_id": scope.get("frame_id"),
            "region": scope.get("region"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _parameter_key(constraint: Mapping[str, Any]) -> str:
    return json.dumps(_parameters(constraint), sort_keys=True, separators=(",", ":"))


def resolve_constraints(
    document: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
) -> JsonObject:
    metadata = document.get("metadata", {})
    metadata = metadata if isinstance(metadata, Mapping) else {}
    version = int(metadata.get("document_version", 0))
    active = [constraint for constraint in constraints if constraint.get("active") is True]
    stale = sorted(
        str(constraint.get("id"))
        for constraint in active
        if constraint.get("document_version") is not None
        and constraint.get("document_version") != version
    )
    current = [constraint for constraint in active if str(constraint.get("id")) not in stale]
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for constraint in current:
        groups.setdefault(_scope_key(constraint), []).append(constraint)

    effective: list[Mapping[str, Any]] = []
    conflicts: list[JsonObject] = []
    for bucket in groups.values():
        ordered = sorted(
            bucket,
            key=lambda item: (
                -SOURCE_PRECEDENCE.get(str(item.get("source")), 0),
                -int(item.get("priority", 0)),
                str(item.get("id")),
            ),
        )
        winner = ordered[0]
        rank = SOURCE_PRECEDENCE.get(str(winner.get("source")), 0)
        priority = int(winner.get("priority", 0))
        peers = [
            item
            for item in ordered
            if SOURCE_PRECEDENCE.get(str(item.get("source")), 0) == rank
            and int(item.get("priority", 0)) == priority
        ]
        if len(peers) > 1 and len({_parameter_key(item) for item in peers}) > 1:
            conflicts.append(
                {
                    "constraint_ids": sorted(str(item.get("id")) for item in peers),
                    "reason_code": "CONSTRAINT_CONFLICT",
                    "target_ids": sorted(_target_ids(winner)),
                }
            )
        else:
            effective.append(winner)
    return {
        "constraints": sorted(effective, key=lambda item: str(item.get("id"))),
        "conflicts": sorted(
            conflicts,
            key=lambda item: ":".join(item["constraint_ids"]),
        ),
        "stale_constraint_ids": stale,
    }


def validate_override(
    document: Mapping[str, Any],
    constraint: Mapping[str, Any],
    token: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    if constraint.get("source") == "SAFETY_SYSTEM":
        return False, "SAFETY_CONSTRAINT_NOT_OVERRIDABLE"
    if token.get("constraint_id") != constraint.get("id"):
        return False, "OVERRIDE_CONSTRAINT_MISMATCH"
    if token.get("document_id") != document.get("document_id"):
        return False, "OVERRIDE_DOCUMENT_MISMATCH"
    metadata = document.get("metadata", {})
    metadata = metadata if isinstance(metadata, Mapping) else {}
    if token.get("document_version") != metadata.get("document_version", 0):
        return False, "OVERRIDE_STALE_VERSION"
    if not str(token.get("actor", "")).strip() or not str(token.get("reason", "")).strip():
        return False, "OVERRIDE_AUDIT_FIELDS_REQUIRED"
    if token.get("one_time") is True and token.get("consumed") is True:
        return False, "OVERRIDE_ALREADY_CONSUMED"
    expires_at = token.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False, "OVERRIDE_EXPIRED"
        if expiry <= (now or datetime.now(UTC)):
            return False, "OVERRIDE_EXPIRED"
    return True, None


def _overridden(
    document: Mapping[str, Any],
    constraint: Mapping[str, Any],
    overrides: Sequence[Mapping[str, Any]],
) -> bool:
    return any(validate_override(document, constraint, token)[0] for token in overrides)


def consume_override_token(token: Mapping[str, Any]) -> JsonObject:
    value = dict(token)
    if value.get("one_time") is True:
        value["consumed"] = True
    return value


def _changed(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    keys: Sequence[str],
    tolerance: float,
) -> bool:
    return any(
        not _close(_number(before.get(key)), _number(after.get(key)), tolerance)
        for key in keys
    )


def _safe_area_bounds(
    after_nodes: Mapping[str, Any],
    target: Mapping[str, Any],
    constraint: Mapping[str, Any],
) -> JsonObject | None:
    scope = _scope(constraint)
    region = scope.get("region")
    if not isinstance(region, Mapping):
        return None
    frame_id = scope.get("frame_id") or target.get("parent_id")
    frame = after_nodes.get(frame_id) if isinstance(frame_id, str) else None
    if not isinstance(frame, Mapping):
        return None
    frame_bounds = _bounds(frame)
    return {
        "x": _number(frame_bounds["x"])
        + _number(region.get("x")) * _number(frame_bounds["width"]),
        "y": _number(frame_bounds["y"])
        + _number(region.get("y")) * _number(frame_bounds["height"]),
        "width": _number(region.get("width")) * _number(frame_bounds["width"]),
        "height": _number(region.get("height")) * _number(frame_bounds["height"]),
    }


def evaluate_deterministic_constraint(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    constraint: Mapping[str, Any],
    *,
    tolerance: Mapping[str, float] = DEFAULT_TOLERANCE,
) -> list[JsonObject]:
    constraint_type = str(constraint.get("type"))
    before_nodes = before.get("nodes", {})
    after_nodes = after.get("nodes", {})
    before_nodes = before_nodes if isinstance(before_nodes, Mapping) else {}
    after_nodes = after_nodes if isinstance(after_nodes, Mapping) else {}
    violations: list[JsonObject] = []

    for target_id in _target_ids(constraint):
        before_node = before_nodes.get(target_id)
        after_node = after_nodes.get(target_id)
        before_node = before_node if isinstance(before_node, Mapping) else None
        after_node = after_node if isinstance(after_node, Mapping) else None
        if before_node is None or after_node is None:
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_TARGET_MISSING",
                    target_id=target_id,
                    expected="present" if before_node else "missing",
                    actual="present" if after_node else "missing",
                )
            )
            continue

        before_t = _transform(before_node)
        after_t = _transform(after_node)
        if constraint_type == "LOCK_POSITION" and _changed(
            before_t,
            after_t,
            ("x", "y"),
            tolerance["position_px"],
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_POSITION_CHANGED",
                    target_id=target_id,
                    expected=_bounds(before_node),
                    actual=_bounds(after_node),
                    repair_hint={"action": "restore_position"},
                )
            )
        elif constraint_type == "LOCK_SIZE" and _changed(
            before_t,
            after_t,
            ("width", "height", "scale_x", "scale_y"),
            tolerance["size_px"],
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_SIZE_CHANGED",
                    target_id=target_id,
                    expected=_bounds(before_node),
                    actual=_bounds(after_node),
                    repair_hint={"action": "restore_size"},
                )
            )
        elif constraint_type == "LOCK_ROTATION" and _changed(
            before_t,
            after_t,
            ("rotation_deg",),
            tolerance["rotation_deg"],
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_ROTATION_CHANGED",
                    target_id=target_id,
                    expected=_number(before_t.get("rotation_deg")),
                    actual=_number(after_t.get("rotation_deg")),
                )
            )
        elif constraint_type == "LOCK_TRANSFORM" and _changed(
            before_t,
            after_t,
            (
                "x",
                "y",
                "width",
                "height",
                "rotation_deg",
                "scale_x",
                "scale_y",
                "skew_x",
                "skew_y",
                "anchor_x",
                "anchor_y",
            ),
            max(
                tolerance["position_px"],
                tolerance["size_px"],
                tolerance["rotation_deg"],
            ),
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_TRANSFORM_CHANGED",
                    target_id=target_id,
                    expected=before_t,
                    actual=after_t,
                    repair_hint={"action": "restore_transform"},
                )
            )
        elif constraint_type == "LOCK_PARENT" and (
            before_node.get("parent_id") != after_node.get("parent_id")
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_PARENT_CHANGED",
                    target_id=target_id,
                    expected=before_node.get("parent_id"),
                    actual=after_node.get("parent_id"),
                )
            )
        elif constraint_type == "LOCK_TEXT" and (
            before_node.get("content") != after_node.get("content")
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_TEXT_CHANGED",
                    target_id=target_id,
                    expected=before_node.get("content"),
                    actual=after_node.get("content"),
                )
            )
        elif constraint_type == "LOCK_ASSET" and (
            before_node.get("asset_id") != after_node.get("asset_id")
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_ASSET_CHANGED",
                    target_id=target_id,
                    expected=before_node.get("asset_id"),
                    actual=after_node.get("asset_id"),
                )
            )
        elif constraint_type == "LOCK_STYLE" and (
            before_node.get("style_refs", []) != after_node.get("style_refs", [])
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_STYLE_CHANGED",
                    target_id=target_id,
                    expected=before_node.get("style_refs", []),
                    actual=after_node.get("style_refs", []),
                )
            )
        elif constraint_type == "LOCK_BRAND" and (
            before_node.get("brand_binding") != after_node.get("brand_binding")
        ):
            violations.append(
                _violation(
                    constraint,
                    "deterministic-ir",
                    "CONSTRAINT_BRAND_BINDING_CHANGED",
                    target_id=target_id,
                    expected=before_node.get("brand_binding"),
                    actual=after_node.get("brand_binding"),
                )
            )
        elif constraint_type == "LOCK_ASPECT_RATIO":
            before_b = _bounds(before_node)
            after_b = _bounds(after_node)
            before_height = _number(before_b.get("height"))
            after_height = _number(after_b.get("height"))
            fallback = _number(before_b.get("width")) / before_height if before_height else 0.0
            expected_ratio = _number(_parameters(constraint).get("ratio"), fallback)
            actual_ratio = _number(after_b.get("width")) / after_height if after_height else 0.0
            if not _close(expected_ratio, actual_ratio, tolerance["aspect_ratio"]):
                violations.append(
                    _violation(
                        constraint,
                        "deterministic-ir",
                        "CONSTRAINT_ASPECT_RATIO_CHANGED",
                        target_id=target_id,
                        expected=expected_ratio,
                        actual=actual_ratio,
                    )
                )
        elif constraint_type == "LOCK_LAYER_ORDER":
            parent_id = before_node.get("parent_id")
            before_parent = before_nodes.get(parent_id) if isinstance(parent_id, str) else None
            after_parent = after_nodes.get(parent_id) if isinstance(parent_id, str) else None
            before_children = (
                before_parent.get("children", []) if isinstance(before_parent, Mapping) else []
            )
            after_children = (
                after_parent.get("children", []) if isinstance(after_parent, Mapping) else []
            )
            before_index = before_children.index(target_id) if target_id in before_children else -1
            after_index = after_children.index(target_id) if target_id in after_children else -1
            if before_index != after_index:
                violations.append(
                    _violation(
                        constraint,
                        "deterministic-ir",
                        "CONSTRAINT_LAYER_ORDER_CHANGED",
                        target_id=target_id,
                        expected=before_index,
                        actual=after_index,
                    )
                )
        elif constraint_type == "LOCK_CONTENT":
            keys = ("content", "asset_id", "source_artifact_version_id", "semantic")
            expected = {key: before_node.get(key) for key in keys}
            actual = {key: after_node.get(key) for key in keys}
            if expected != actual:
                violations.append(
                    _violation(
                        constraint,
                        "deterministic-ir",
                        "CONSTRAINT_CONTENT_CHANGED",
                        target_id=target_id,
                        expected=expected,
                        actual=actual,
                    )
                )

    if constraint_type == "MUST_NOT_OVERLAP":
        forbidden = _parameters(constraint).get("forbidden_node_ids", [])
        if not isinstance(forbidden, Sequence) or isinstance(forbidden, str | bytes):
            forbidden = []
        for target_id in _target_ids(constraint):
            target = after_nodes.get(target_id)
            if not isinstance(target, Mapping):
                continue
            for forbidden_id in forbidden:
                other = after_nodes.get(forbidden_id)
                if (
                    isinstance(forbidden_id, str)
                    and isinstance(other, Mapping)
                    and _intersects(
                        _bounds(target),
                        _bounds(other),
                        tolerance["overlap_px"],
                    )
                ):
                    violations.append(
                        _violation(
                            constraint,
                            "deterministic-ir",
                            "CONSTRAINT_OVERLAP",
                            target_id=target_id,
                            expected=forbidden_id,
                            actual={"target": _bounds(target), "forbidden": _bounds(other)},
                        )
                    )

    if constraint_type in {"MUST_STAY_INSIDE", "MIN_MARGIN"}:
        parameters = _parameters(constraint)
        container_id = parameters.get("container_id") or _scope(constraint).get("frame_id")
        container = after_nodes.get(container_id) if isinstance(container_id, str) else None
        if isinstance(container, Mapping):
            margin = _number(parameters.get("min_px")) if constraint_type == "MIN_MARGIN" else 0.0
            for target_id in _target_ids(constraint):
                target = after_nodes.get(target_id)
                if not isinstance(target, Mapping):
                    continue
                if _inside(
                    _bounds(target),
                    _bounds(container),
                    margin,
                    tolerance["position_px"],
                ):
                    continue
                reason = (
                    "CONSTRAINT_MARGIN_TOO_SMALL"
                    if constraint_type == "MIN_MARGIN"
                    else "CONSTRAINT_OUTSIDE_CONTAINER"
                )
                violations.append(
                    _violation(
                        constraint,
                        "deterministic-ir",
                        reason,
                        target_id=target_id,
                        expected={"container": _bounds(container), "margin": margin},
                        actual=_bounds(target),
                    )
                )

    if constraint_type == "SAFE_AREA":
        for target_id in _target_ids(constraint):
            target = after_nodes.get(target_id)
            if not isinstance(target, Mapping):
                continue
            safe = _safe_area_bounds(after_nodes, target, constraint)
            if safe is None:
                violations.append(
                    _violation(
                        constraint,
                        "deterministic-ir",
                        "CONSTRAINT_SAFE_AREA_FRAME_MISSING",
                        target_id=target_id,
                        repair_hint={"action": "bind_safe_area_frame"},
                    )
                )
            elif not _inside(_bounds(target), safe, 0.0, tolerance["position_px"]):
                violations.append(
                    _violation(
                        constraint,
                        "deterministic-ir",
                        "CONSTRAINT_OUTSIDE_SAFE_AREA",
                        target_id=target_id,
                        expected=safe,
                        actual=_bounds(target),
                        repair_hint={"action": "move_inside_safe_area"},
                    )
                )
    return violations


def aggregate_violations(violations: Iterable[Mapping[str, Any]]) -> list[JsonObject]:
    rank = {"HARD": 3, "SOFT": 2, "ADVISORY": 1}
    result: dict[tuple[str, str, str, str], JsonObject] = {}
    for raw in violations:
        violation = dict(raw)
        key = (
            str(violation.get("constraint_id", "")),
            str(violation.get("target_id", "")),
            str(violation.get("validator", "")),
            str(violation.get("reason_code", "")),
        )
        current = result.get(key)
        if current is None or rank.get(str(violation.get("severity")), 0) > rank.get(
            str(current.get("severity")),
            0,
        ):
            result[key] = violation
    return sorted(
        result.values(),
        key=lambda item: (
            -rank.get(str(item.get("severity")), 0),
            str(item.get("constraint_id")),
            str(item.get("reason_code")),
        ),
    )


def guarded_execute(
    document: JsonObject,
    operations: list[JsonObject],
    constraints: Sequence[Mapping[str, Any]],
    *,
    overrides: Sequence[Mapping[str, Any]] = (),
    tolerance: Mapping[str, float] = DEFAULT_TOLERANCE,
) -> JsonObject:
    resolved = resolve_constraints(document, constraints)
    by_id = {str(item.get("id")): item for item in constraints}
    violations: list[JsonObject] = []
    for conflict in resolved["conflicts"]:
        ids = conflict["constraint_ids"]
        first = by_id[str(ids[0])]
        violations.append(
            _violation(
                first,
                "constraint-resolver",
                "CONSTRAINT_CONFLICT",
                expected=ids,
                repair_hint={"action": "resolve_constraint_conflict"},
            )
        )
    for constraint_id in resolved["stale_constraint_ids"]:
        constraint = by_id[str(constraint_id)]
        violation = _violation(
            constraint,
            "constraint-resolver",
            "STALE_CONSTRAINT_SNAPSHOT",
            expected=constraint.get("document_version"),
            repair_hint={"action": "refresh_constraint_snapshot"},
        )
        if violation["severity"] != "HARD":
            violation["severity"] = "SOFT"
        violations.append(violation)
    if any(item.get("severity") == "HARD" for item in violations):
        return {
            "preflight": {
                "decision": "DENY",
                "violations": aggregate_violations(violations),
                "conflicts": resolved["conflicts"],
                "effective_constraint_ids": [
                    item.get("id") for item in resolved["constraints"]
                ],
            }
        }

    execution = execute_operations(document, operations)
    if not execution.get("ok"):
        return {
            "preflight": {
                "decision": "DENY",
                "violations": violations,
                "conflicts": resolved["conflicts"],
                "effective_constraint_ids": [
                    item.get("id") for item in resolved["constraints"]
                ],
            },
            "execution": execution,
        }

    candidate = execution["document"]
    for constraint in resolved["constraints"]:
        if _overridden(document, constraint, overrides):
            continue
        violations.extend(
            evaluate_deterministic_constraint(
                document,
                candidate,
                constraint,
                tolerance=tolerance,
            )
        )
    aggregated = aggregate_violations(violations)
    if any(item.get("severity") == "HARD" for item in aggregated):
        decision = "DENY"
    elif aggregated:
        decision = "ALLOW_WITH_WARNINGS"
    else:
        decision = "ALLOW"
    result: JsonObject = {
        "preflight": {
            "decision": decision,
            "violations": aggregated,
            "conflicts": resolved["conflicts"],
            "effective_constraint_ids": [item.get("id") for item in resolved["constraints"]],
        }
    }
    if decision != "DENY":
        result["execution"] = execution
    return result


def postflight_validate(
    context: Mapping[str, Any],
    evaluators: Sequence[PostflightEvaluator],
) -> JsonObject:
    constraints = context.get("constraints", [])
    constraints = constraints if isinstance(constraints, Sequence) else []
    document = context.get("document", {})
    document = document if isinstance(document, Mapping) else {}
    overrides = context.get("overrides", [])
    overrides = overrides if isinstance(overrides, Sequence) else []
    valid_overrides = [item for item in overrides if isinstance(item, Mapping)]
    violations: list[JsonObject] = []
    unavailable: set[str] = set()

    for constraint in constraints:
        if not isinstance(constraint, Mapping) or constraint.get("active") is not True:
            continue
        if _overridden(document, constraint, valid_overrides):
            continue
        constraint_type = str(constraint.get("type"))
        matching = [item for item in evaluators if constraint_type in item.supported_types]
        if not matching:
            if constraint.get("severity") == "HARD" and constraint_type in POSTFLIGHT_REQUIRED_TYPES:
                validator = f"missing:{constraint_type}"
                unavailable.add(validator)
                violations.append(
                    _violation(
                        constraint,
                        validator,
                        "VALIDATION_UNAVAILABLE",
                        repair_hint={"action": "retry_or_manual_review"},
                    )
                )
            continue
        for evaluator in matching:
            try:
                violations.extend(evaluator.evaluate(context, constraint))
            except Exception:  # noqa: BLE001
                unavailable.add(evaluator.name)
                if constraint.get("severity") == "HARD":
                    violations.append(
                        _violation(
                            constraint,
                            evaluator.name,
                            "VALIDATION_UNAVAILABLE",
                            repair_hint={"action": "retry_or_manual_review"},
                        )
                    )

    aggregated = aggregate_violations(violations)
    if any(item.get("severity") == "HARD" for item in aggregated):
        decision = "FAIL"
    elif any(item.get("severity") == "SOFT" for item in aggregated):
        decision = "REPAIR"
    else:
        decision = "PASS"
    return {
        "decision": decision,
        "violations": aggregated,
        "unavailable_validators": sorted(unavailable),
    }


def build_constraint_snapshot(
    document: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
) -> JsonObject:
    resolved = resolve_constraints(document, constraints)
    metadata = document.get("metadata", {})
    metadata = metadata if isinstance(metadata, Mapping) else {}
    return {
        "document_id": str(document.get("document_id", "")),
        "document_version": int(metadata.get("document_version", 0)),
        "effective_constraints": deepcopy(resolved["constraints"]),
        "conflicts": deepcopy(resolved["conflicts"]),
        "stale_constraint_ids": list(resolved["stale_constraint_ids"]),
    }


def constraint_snapshot_hash(
    document: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
) -> str:
    return canonical_sha256(build_constraint_snapshot(document, constraints))


def summarize_constraints_for_agent(
    document: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
) -> list[JsonObject]:
    resolved = resolve_constraints(document, constraints)
    return [
        {
            "id": str(constraint.get("id")),
            "type": str(constraint.get("type")),
            "severity": str(constraint.get("severity")),
            "node_ids": _target_ids(constraint),
            "parameters": deepcopy(_parameters(constraint)),
        }
        for constraint in resolved["constraints"]
    ]
