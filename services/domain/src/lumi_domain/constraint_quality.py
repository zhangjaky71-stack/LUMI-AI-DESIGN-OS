from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _parse_hex(value: str) -> tuple[int, int, int] | None:
    normalized = value.strip().removeprefix("#")
    if len(normalized) == 3:
        normalized = "".join(part * 2 for part in normalized)
    if len(normalized) != 6:
        return None
    try:
        return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def _channel(value: int) -> float:
    srgb = value / 255.0
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float | None:
    parsed = _parse_hex(color)
    if parsed is None:
        return None
    red, green, blue = parsed
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(foreground: str, background: str) -> float | None:
    foreground_luminance = relative_luminance(foreground)
    background_luminance = relative_luminance(background)
    if foreground_luminance is None or background_luminance is None:
        return None
    lighter = max(foreground_luminance, background_luminance)
    darker = min(foreground_luminance, background_luminance)
    return (lighter + 0.05) / (darker + 0.05)


class StructuredContrastEvaluator:
    name = "structured-contrast"
    supported_types = frozenset({"REQUIRE_CONTRAST", "REQUIRE_TEXT_READABILITY"})

    def evaluate(
        self,
        _context: Mapping[str, Any],
        constraint: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        parameters = constraint.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise RuntimeError("constraint parameters are required")
        foreground = parameters.get("foreground")
        background = parameters.get("background")
        minimum = parameters.get("min_ratio", 4.5)
        if not isinstance(foreground, str) or not isinstance(background, str):
            raise RuntimeError(
                "Structured contrast requires colors; use a sampling plugin for image backgrounds"
            )
        if isinstance(minimum, bool) or not isinstance(minimum, int | float):
            raise RuntimeError("min_ratio must be numeric")
        ratio = contrast_ratio(foreground, background)
        if ratio is None:
            raise RuntimeError("unsupported color format")
        if ratio >= float(minimum):
            return []
        return [
            {
                "constraint_id": str(constraint.get("id", "unknown")),
                "type": str(constraint.get("type", "REQUIRE_CONTRAST")),
                "severity": str(constraint.get("severity", "HARD")),
                "validator": self.name,
                "reason_code": "CONTRAST_BELOW_PROFILE_THRESHOLD",
                "score": ratio,
                "threshold": float(minimum),
                "expected": float(minimum),
                "actual": ratio,
                "repair_hint": {"action": "increase_contrast"},
            }
        ]
