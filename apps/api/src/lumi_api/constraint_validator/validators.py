from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .contracts import (
    ConstraintViolation,
    RuntimeConstraint,
    ValidationAdapters,
    ValidationPolicy,
    make_violation,
)
from .geometry import contrast_ratio, inside, overlaps, ratio, rect_for_node

ValidatorFn = Callable[
    [Mapping[str, Any], RuntimeConstraint, set[str], ValidationAdapters, ValidationPolicy],
    tuple[ConstraintViolation, ...],
]


@dataclass(frozen=True, slots=True)
class ValidatorSpec:
    name: str
    constraint_types: tuple[str, ...]
    fn: ValidatorFn


def _nodes(document: Mapping[str, Any]) -> Mapping[str, Any]:
    value = document.get("nodes", {})
    return value if isinstance(value, Mapping) else {}


def _targets(document, constraint, impact):
    nodes = _nodes(document)
    if constraint.scope.node_ids:
        values = set(constraint.scope.node_ids)
    elif constraint.scope.semantic_tags:
        tags = set(constraint.scope.semantic_tags)
        values = {
            node_id
            for node_id, node in nodes.items()
            if isinstance(node, Mapping)
            and (node.get("role") in tags or bool(set(node.get("semantic_tags", ())) & tags))
        }
    else:
        values = set(nodes)
    if impact:
        values &= impact
    return tuple(sorted(str(value) for value in values if value in nodes))


def _region(constraint):
    raw = constraint.scope.region or constraint.parameters.get("region")
    if not isinstance(raw, Mapping):
        return None
    try:
        return (float(raw.get("x", 0)), float(raw.get("y", 0)), float(raw["width"]), float(raw["height"]))
    except (KeyError, TypeError, ValueError):
        return None


def _issue(constraint, validator, node_id, code, message, policy, *, measured=None, expected=None, unavailable=False):
    return make_violation(
        constraint=constraint,
        validator=validator,
        node_ids=(node_id,),
        message_code=code,
        message=message,
        measured=measured,
        expected=expected,
        unavailable=unavailable,
        policy=policy,
    )


def validate_bounds(document, constraint, impact, adapters, policy):
    del adapters
    outer = _region(constraint)
    if outer is None:
        return ()
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        box = rect_for_node(nodes[node_id])
        if box is not None and not inside(box, outer):
            result.append(_issue(constraint, "BoundsValidator", node_id, "NODE_OUT_OF_BOUNDS", "Node must remain inside the allowed bounds.", policy, measured=box, expected=outer))
    return tuple(result)


def validate_safe_area(document, constraint, impact, adapters, policy):
    del adapters
    outer = _region(constraint)
    if outer is None:
        return ()
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        box = rect_for_node(nodes[node_id])
        if box is not None and not inside(box, outer):
            result.append(_issue(constraint, "SafeAreaValidator", node_id, "SAFE_AREA_VIOLATION", "Node crosses the configured safe area.", policy, measured=box, expected=outer))
    return tuple(result)


def validate_locked(document, constraint, impact, adapters, policy):
    del adapters
    return tuple(_issue(constraint, "LockedRegionValidator", node_id, "LOCKED_NODE_MUTATION", "The operation violates an active lock constraint.", policy, measured="mutation", expected="unchanged") for node_id in _targets(document, constraint, impact))


def validate_text_overflow(document, constraint, impact, adapters, policy):
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        node = nodes[node_id]
        if node.get("kind") != "TEXT":
            continue
        needs_exact = constraint.parameters.get("require_measurement", True) or any(ord(ch) > 127 for ch in str(node.get("content", "")))
        if adapters.text_measure is None:
            if needs_exact:
                result.append(_issue(constraint, "TextOverflowValidator", node_id, "TEXT_MEASUREMENT_UNAVAILABLE", "Exact text measurement is unavailable; overflow cannot be proven safe.", policy, unavailable=True))
            continue
        try:
            measured = adapters.text_measure(node)
        except Exception:
            result.append(_issue(constraint, "TextOverflowValidator", node_id, "TEXT_MEASUREMENT_FAILED", "Text measurement adapter failed; overflow cannot be proven safe.", policy, unavailable=True))
            continue
        box = rect_for_node(node)
        if box is None:
            continue
        width, height = float(measured.get("width", 0)), float(measured.get("height", 0))
        if width > box[2] or height > box[3]:
            result.append(_issue(constraint, "TextOverflowValidator", node_id, "TEXT_OVERFLOW", "Measured text exceeds the text box.", policy, measured={"width": width, "height": height}, expected={"width": box[2], "height": box[3]}))
        max_lines = constraint.parameters.get("max_lines")
        if isinstance(max_lines, int) and measured.get("lines", 0) > max_lines:
            result.append(_issue(constraint, "TextOverflowValidator", node_id, "TEXT_MAX_LINES", "Text exceeds the configured maximum line count.", policy, measured=measured.get("lines"), expected=max_lines))
    return tuple(result)


def validate_font_size(document, constraint, impact, adapters, policy):
    del adapters
    minimum = float(constraint.parameters.get("min_font_size", 12))
    forbidden = set(constraint.parameters.get("forbidden_fonts", ()))
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        node = nodes[node_id]
        if node.get("kind") != "TEXT":
            continue
        size = node.get("font_size")
        if isinstance(size, (int, float)) and size < minimum:
            result.append(_issue(constraint, "FontSizeValidator", node_id, "FONT_SIZE_TOO_SMALL", "Text is smaller than the configured minimum font size.", policy, measured=size, expected=minimum))
        family = node.get("font_family")
        if isinstance(family, str) and family in forbidden:
            result.append(_issue(constraint, "FontSizeValidator", node_id, "FORBIDDEN_FONT", "The selected font is forbidden by the active rule.", policy, measured=family, expected="allowed font"))
        line_height = node.get("line_height")
        if isinstance(size, (int, float)) and size > 0 and isinstance(line_height, (int, float)):
            current = float(line_height) / float(size)
            low = float(constraint.parameters.get("min_line_height_ratio", 0.8))
            high = float(constraint.parameters.get("max_line_height_ratio", 2.0))
            if current < low or current > high:
                result.append(_issue(constraint, "FontSizeValidator", node_id, "LINE_HEIGHT_UNREASONABLE", "Text line height is outside the configured readability range.", policy, measured=current, expected={"min": low, "max": high}))
    return tuple(result)


def validate_aspect_ratio(document, constraint, impact, adapters, policy):
    del adapters
    expected = constraint.parameters.get("ratio")
    if not isinstance(expected, (int, float)):
        return ()
    tolerance = float(constraint.parameters.get("tolerance", 0.01))
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        box = rect_for_node(nodes[node_id])
        current = ratio(box) if box is not None else None
        if current is not None and abs(current - float(expected)) > tolerance:
            result.append(_issue(constraint, "AspectRatioValidator", node_id, "ASPECT_RATIO_MISMATCH", "Node aspect ratio exceeds the permitted tolerance.", policy, measured=current, expected=expected))
    return tuple(result)


def validate_contrast(document, constraint, impact, adapters, policy):
    del adapters
    minimum = float(constraint.parameters.get("min_ratio", 4.5))
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        node = nodes[node_id]
        fg = node.get("fill") or node.get("foreground")
        bg = node.get("background") or constraint.parameters.get("background")
        if not isinstance(fg, str) or not isinstance(bg, str):
            continue
        current = contrast_ratio(fg, bg)
        if current is not None and current < minimum:
            result.append(_issue(constraint, "ContrastValidator", node_id, "CONTRAST_TOO_LOW", "Foreground/background contrast is below the required ratio.", policy, measured=current, expected=minimum))
    return tuple(result)


def validate_protected_region(document, constraint, impact, adapters, policy):
    del adapters
    protected = _region(constraint)
    if protected is None:
        return ()
    allowed = set(constraint.parameters.get("allowed_node_ids", ()))
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        if node_id in allowed:
            continue
        box = rect_for_node(nodes[node_id])
        if box is not None and overlaps(box, protected):
            result.append(_issue(constraint, "ProtectedRegionValidator", node_id, "PROTECTED_REGION_OVERLAP", "Node overlaps a protected region.", policy, measured=box, expected={"no_overlap": protected}))
    return tuple(result)


def validate_qr(document, constraint, impact, adapters, policy):
    minimum = float(constraint.parameters.get("min_size_px", 96))
    quiet = float(constraint.parameters.get("quiet_zone_px", 8))
    scale = float(constraint.parameters.get("output_scale", 1))
    require_decode = bool(constraint.parameters.get("require_decode", True))
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        node = nodes[node_id]
        if node.get("role") != "QR_CODE" and not constraint.scope.node_ids:
            continue
        box = rect_for_node(node)
        if box is None:
            continue
        effective = min(box[2], box[3]) * scale
        if effective < minimum:
            result.append(_issue(constraint, "QRValidator", node_id, "QR_TOO_SMALL", "QR effective raster size is below the configured minimum.", policy, measured=effective, expected=minimum))
        actual_quiet = node.get("quiet_zone_px", constraint.parameters.get("node_quiet_zone_px", quiet))
        if isinstance(actual_quiet, (int, float)) and float(actual_quiet) < quiet:
            result.append(_issue(constraint, "QRValidator", node_id, "QR_QUIET_ZONE_TOO_SMALL", "QR quiet zone is smaller than required.", policy, measured=actual_quiet, expected=quiet))
        fg, bg = node.get("foreground", "#000000"), node.get("background", "#ffffff")
        if isinstance(fg, str) and isinstance(bg, str):
            current = contrast_ratio(fg, bg)
            required = float(constraint.parameters.get("min_contrast_ratio", 4.5))
            if current is not None and current < required:
                result.append(_issue(constraint, "QRValidator", node_id, "QR_CONTRAST_TOO_LOW", "QR contrast is below the scannability threshold.", policy, measured=current, expected=required))
        if not require_decode:
            continue
        if adapters.qr_decode is None:
            result.append(_issue(constraint, "QRValidator", node_id, "QR_DECODE_UNAVAILABLE", "Raster QR decoder is unavailable; scannability cannot be proven.", policy, unavailable=True))
            continue
        try:
            decoded = adapters.qr_decode(node)
        except Exception:
            result.append(_issue(constraint, "QRValidator", node_id, "QR_DECODE_ADAPTER_FAILED", "QR decoder failed; scannability cannot be proven.", policy, unavailable=True))
        else:
            if not decoded:
                result.append(_issue(constraint, "QRValidator", node_id, "QR_DECODE_FAILED", "Rendered QR could not be decoded.", policy, measured=False, expected=True))
    return tuple(result)


def validate_brand(document, constraint, impact, adapters, policy):
    del adapters
    colors = set(constraint.parameters.get("allowed_colors", ()))
    fonts = set(constraint.parameters.get("allowed_fonts", ()))
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        node = nodes[node_id]
        if colors and isinstance(node.get("fill"), str) and node["fill"] not in colors:
            result.append(_issue(constraint, "BrandTokenValidator", node_id, "BRAND_COLOR_FORBIDDEN", "Node uses a color outside the approved brand token set.", policy, measured=node["fill"], expected=sorted(colors)))
        if fonts and isinstance(node.get("font_family"), str) and node["font_family"] not in fonts:
            result.append(_issue(constraint, "BrandTokenValidator", node_id, "BRAND_FONT_FORBIDDEN", "Node uses a font outside the approved brand token set.", policy, measured=node["font_family"], expected=sorted(fonts)))
        transform = node.get("transform") or {}
        rotation = transform.get("rotation_deg", 0) if isinstance(transform, Mapping) else 0
        if node.get("role") == "LOGO" and constraint.parameters.get("logo_rotation_forbidden", True) and rotation not in (0, 0.0):
            result.append(_issue(constraint, "BrandTokenValidator", node_id, "LOGO_TRANSFORM_FORBIDDEN", "Logo rotation is forbidden by the brand rule.", policy, measured=rotation, expected=0))
    return tuple(result)


def validate_identity(document, constraint, impact, adapters, policy):
    threshold = float(constraint.parameters.get("min_score", 0.90))
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        node = nodes[node_id]
        if adapters.identity_score is None:
            result.append(_issue(constraint, "IdentityPreservationValidator", node_id, "IDENTITY_BASELINE_UNAVAILABLE", "Identity feature baseline is unavailable; preservation cannot be proven.", policy, unavailable=True))
            continue
        try:
            score = adapters.identity_score(node)
        except Exception:
            result.append(_issue(constraint, "IdentityPreservationValidator", node_id, "IDENTITY_ADAPTER_FAILED", "Identity validator failed; preservation cannot be proven.", policy, unavailable=True))
            continue
        if score is None:
            result.append(_issue(constraint, "IdentityPreservationValidator", node_id, "IDENTITY_SCORE_UNAVAILABLE", "Identity score could not be produced.", policy, unavailable=True))
        elif score < threshold:
            result.append(_issue(constraint, "IdentityPreservationValidator", node_id, "IDENTITY_SCORE_TOO_LOW", "Identity preservation score is below the configured threshold.", policy, measured=score, expected=threshold))
    return tuple(result)


def validate_export_dimension(document, constraint, impact, adapters, policy):
    del adapters
    width, height = constraint.parameters.get("width"), constraint.parameters.get("height")
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        return ()
    result = []
    nodes = _nodes(document)
    for node_id in _targets(document, constraint, impact):
        node = nodes[node_id]
        if node.get("kind") != "FRAME":
            continue
        box = rect_for_node(node)
        if box is not None and (box[2] != float(width) or box[3] != float(height)):
            result.append(_issue(constraint, "ExportDimensionValidator", node_id, "EXPORT_DIMENSION_MISMATCH", "Frame dimensions do not match the export contract.", policy, measured={"width": box[2], "height": box[3]}, expected={"width": width, "height": height}))
    return tuple(result)


VALIDATOR_SPECS = (
    ValidatorSpec("BoundsValidator", ("MUST_STAY_INSIDE",), validate_bounds),
    ValidatorSpec("SafeAreaValidator", ("SAFE_AREA",), validate_safe_area),
    ValidatorSpec("LockedRegionValidator", ("LOCK_POSITION", "LOCK_SIZE", "LOCK_ROTATION", "LOCK_TRANSFORM", "LOCK_LAYER_ORDER", "LOCK_PARENT", "LOCK_CONTENT", "LOCK_TEXT", "LOCK_ASSET", "LOCK_STYLE"), validate_locked),
    ValidatorSpec("TextOverflowValidator", ("REQUIRE_TEXT_READABILITY",), validate_text_overflow),
    ValidatorSpec("FontSizeValidator", ("REQUIRE_TEXT_READABILITY",), validate_font_size),
    ValidatorSpec("AspectRatioValidator", ("LOCK_ASPECT_RATIO",), validate_aspect_ratio),
    ValidatorSpec("ContrastValidator", ("REQUIRE_CONTRAST",), validate_contrast),
    ValidatorSpec("ProtectedRegionValidator", ("PROTECT_REGION", "MUST_NOT_OVERLAP"), validate_protected_region),
    ValidatorSpec("QRValidator", ("REQUIRE_SCANNABILITY",), validate_qr),
    ValidatorSpec("BrandTokenValidator", ("REQUIRE_BRAND_COMPLIANCE", "LOCK_BRAND"), validate_brand),
    ValidatorSpec("IdentityPreservationValidator", ("REQUIRE_IDENTITY_SCORE", "LOCK_IDENTITY"), validate_identity),
    ValidatorSpec("ExportDimensionValidator", ("REQUIRE_RESOLUTION",), validate_export_dimension),
)


def relevant_specs(constraint: RuntimeConstraint) -> tuple[ValidatorSpec, ...]:
    return tuple(spec for spec in VALIDATOR_SPECS if constraint.type in spec.constraint_types)
