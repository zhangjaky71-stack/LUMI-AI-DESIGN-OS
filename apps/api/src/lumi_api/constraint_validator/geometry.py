from __future__ import annotations

import math
from typing import Any, Mapping


def rect_for_node(node: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    source = (
        node.get("bounds")
        if isinstance(node.get("bounds"), Mapping)
        else node.get("transform")
    )
    if not isinstance(source, Mapping):
        return None
    try:
        x = float(source.get("x", 0.0))
        y = float(source.get("y", 0.0))
        width = float(source["width"])
        height = float(source["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x, y, width, height)):
        return None
    return x, y, width, height


def overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def inside(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


def ratio(rect: tuple[float, float, float, float]) -> float | None:
    if rect[3] == 0:
        return None
    return rect[2] / rect[3]


def contrast_ratio(foreground: str, background: str) -> float | None:
    def parse(value: str) -> tuple[int, int, int] | None:
        text = value.removeprefix("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        if len(text) != 6:
            return None
        try:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError:
            return None

    def luminance(rgb: tuple[int, int, int]) -> float:
        values = []
        for channel in rgb:
            value = channel / 255
            values.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]

    left = parse(foreground)
    right = parse(background)
    if left is None or right is None:
        return None
    high, low = sorted((luminance(left), luminance(right)), reverse=True)
    return (high + 0.05) / (low + 0.05)
