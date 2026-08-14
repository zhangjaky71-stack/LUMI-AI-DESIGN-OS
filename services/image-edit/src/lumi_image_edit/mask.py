from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .model import MaskSource, MaskSpec, PixelRect, ProtectedRegion, SourceImageRef


@dataclass(frozen=True, slots=True)
class NormalizedRect:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("IMAGE_EDIT_NORMALIZED_RECT_INVALID")
        if self.width <= 0 or self.height <= 0 or self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("IMAGE_EDIT_NORMALIZED_RECT_INVALID")


def normalized_to_pixels(rect: NormalizedRect, width: int, height: int) -> PixelRect:
    x = round(rect.x * width)
    y = round(rect.y * height)
    right = round((rect.x + rect.width) * width)
    bottom = round((rect.y + rect.height) * height)
    return PixelRect(x=x, y=y, width=max(1, right - x), height=max(1, bottom - y))


def rects_overlap(a: PixelRect, b: PixelRect) -> bool:
    return not (a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y)


def assert_no_hard_protected_overlap(editable: PixelRect, protected: tuple[ProtectedRegion, ...]) -> None:
    for region in protected:
        if region.severity == "HARD" and rects_overlap(editable, region.rect):
            raise ValueError(f"IMAGE_EDIT_MASK_OVERLAPS_HARD_PROTECTED_REGION:{region.region_id}")


def build_mask_spec(
    *,
    source: SourceImageRef,
    mask_id: str,
    version: str,
    source_kind: MaskSource,
    editable_rect: PixelRect,
    mask_bytes: bytes,
    durable_ref: str,
    preview_required: bool = False,
    preview_approved_by: str | None = None,
) -> MaskSpec:
    if not mask_bytes:
        raise ValueError("IMAGE_EDIT_MASK_EMPTY")
    checksum = hashlib.sha256(mask_bytes).hexdigest()
    return MaskSpec(
        mask_id=mask_id,
        version=version,
        source=source_kind,
        source_asset_id=source.asset_id,
        source_asset_version=source.asset_version,
        source_checksum_sha256=source.checksum_sha256,
        source_width=source.width,
        source_height=source.height,
        editable_rect=editable_rect,
        checksum_sha256=checksum,
        durable_ref=durable_ref,
        preview_required=preview_required,
        preview_approved_by=preview_approved_by,
    )
