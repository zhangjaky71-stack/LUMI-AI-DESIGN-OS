from __future__ import annotations

import hashlib

from .model import MaskSpec, PixelRect, ProtectedRegion, SourceImageRef


def normalized_rect_to_pixels(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    source_width: int,
    source_height: int,
) -> PixelRect:
    values = (x, y, width, height)
    if (
        any(value < 0 or value > 1 for value in values)
        or x + width > 1
        or y + height > 1
        or width <= 0
        or height <= 0
    ):
        raise ValueError("IMAGE_EDIT_NORMALIZED_MASK_INVALID")
    left = round(x * source_width)
    top = round(y * source_height)
    right = round((x + width) * source_width)
    bottom = round((y + height) * source_height)
    return PixelRect(
        left,
        top,
        max(1, right - left),
        max(1, bottom - top),
    )


def canonical_mask_hash(
    *,
    source: SourceImageRef,
    rect: PixelRect,
    mask_bytes: bytes,
) -> str:
    digest = hashlib.sha256()
    digest.update(source.checksum_sha256.encode())
    digest.update(
        f"{rect.x},{rect.y},{rect.width},{rect.height}".encode()
    )
    digest.update(mask_bytes)
    return digest.hexdigest()


def validate_mask(
    spec: MaskSpec,
    source: SourceImageRef,
    protected: tuple[ProtectedRegion, ...],
) -> None:
    if spec.source_checksum_sha256 != source.checksum_sha256:
        raise ValueError("IMAGE_EDIT_MASK_SOURCE_CHECKSUM_MISMATCH")
    if spec.preview_required and not spec.preview_approved_by:
        raise PermissionError("IMAGE_EDIT_HIGH_IMPACT_MASK_APPROVAL_REQUIRED")
    for region in protected:
        if region.severity == "HARD" and spec.editable_rect.intersects(region.rect):
            raise ValueError(
                "IMAGE_EDIT_MASK_OVERLAPS_HARD_PROTECTED_REGION:"
                f"{region.region_id}"
            )
