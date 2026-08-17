from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from typing import Literal, Mapping

EditRoute = Literal[
    "STRUCTURAL_IR_EDIT",
    "PIXEL_LOCAL_EDIT",
    "REGENERATE_REGION",
    "FULL_IMAGE_EDIT",
    "HYBRID",
]
EditStatus = Literal[
    "PLANNED",
    "QUEUED",
    "AWAITING_MASK_APPROVAL",
    "AWAITING_CONFIRMATION",
    "RUNNING",
    "PROVIDER_PENDING",
    "VALIDATING",
    "COMPLETED",
    "REPAIR_REQUIRED",
    "REJECTED",
    "FAILED",
    "CANCELLED",
]
MaskSource = Literal["USER_BRUSH", "DESIGN_IR", "DETECTOR", "AGENT_PROPOSED"]
RegionRole = Literal[
    "EDITABLE",
    "PRODUCT",
    "LOGO",
    "QR",
    "LOCKED_TEXT",
    "CONTENT",
]
Severity = Literal["HARD", "SOFT", "ADVISORY"]
ValidationDecision = Literal["PASS", "REPAIR", "REJECT"]


def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("IMAGE_EDIT_NON_FINITE_DECIMAL")
        return format(value, "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("IMAGE_EDIT_NON_FINITE_FLOAT")
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )
    return value


def canonical_hash(value: object) -> str:
    raw = json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if min(self.x, self.y) < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("IMAGE_EDIT_PIXEL_RECT_INVALID")

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def intersects(self, other: PixelRect) -> bool:
        return not (
            self.right <= other.x
            or other.right <= self.x
            or self.bottom <= other.y
            or other.bottom <= self.y
        )
