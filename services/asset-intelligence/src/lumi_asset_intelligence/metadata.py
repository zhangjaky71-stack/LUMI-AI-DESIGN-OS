from __future__ import annotations

from .model import MetadataField

_PRIORITY = {"AUTO": 0, "SYSTEM": 1, "USER": 2}


def merge_metadata(
    current: dict[str, MetadataField],
    incoming: tuple[MetadataField, ...],
) -> dict[str, MetadataField]:
    merged = dict(current)
    for field in incoming:
        existing = merged.get(field.key)
        if existing is None:
            merged[field.key] = field
            continue
        if _PRIORITY[field.source] > _PRIORITY[existing.source]:
            merged[field.key] = field
        elif field.source == existing.source == "AUTO":
            if (field.confidence or 0) > (existing.confidence or 0):
                merged[field.key] = field
    return merged


def system_metadata(
    *, checksum_sha256: str, mime_type: str, media_kind: str, byte_size: int,
    technical: dict[str, object],
) -> tuple[MetadataField, ...]:
    values: dict[str, object] = {
        "checksum_sha256": checksum_sha256,
        "mime_type": mime_type,
        "media_kind": media_kind,
        "byte_size": byte_size,
    }
    values.update(technical)
    return tuple(
        MetadataField(key=key, value=value, source="SYSTEM")
        for key, value in sorted(values.items())
    )


def user_metadata(values: dict[str, object]) -> tuple[MetadataField, ...]:
    return tuple(
        MetadataField(key=key, value=value, source="USER")
        for key, value in sorted(values.items())
    )
