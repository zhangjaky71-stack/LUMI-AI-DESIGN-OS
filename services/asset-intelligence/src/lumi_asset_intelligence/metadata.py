from __future__ import annotations

from collections.abc import Iterable

from .model import MetadataField

_PROTECTED_SYSTEM_FIELDS = frozenset(
    {
        "checksum_sha256",
        "mime_type",
        "media_type",
        "size_bytes",
        "width",
        "height",
        "duration_ms",
        "color_space",
        "has_alpha",
    }
)

_SOURCE_PRIORITY = {"AUTO": 1, "SYSTEM": 2, "USER": 3}


def merge_metadata(
    base: dict[str, MetadataField],
    incoming: Iterable[MetadataField],
) -> dict[str, MetadataField]:
    """Merge field-level metadata without allowing AUTO data to overwrite USER data."""

    merged = dict(base)
    for field in incoming:
        current = merged.get(field.key)
        if current is None:
            merged[field.key] = field
            continue

        if field.key in _PROTECTED_SYSTEM_FIELDS:
            if current.source == "SYSTEM" and field.source != "SYSTEM":
                continue
            if field.source == "SYSTEM":
                merged[field.key] = field
                continue

        if current.source == "USER" and field.source == "AUTO":
            continue
        if _SOURCE_PRIORITY[field.source] >= _SOURCE_PRIORITY[current.source]:
            merged[field.key] = field
    return merged


def system_metadata_from_asset(
    *,
    checksum_sha256: str,
    mime_type: str,
    media_type: str,
    size_bytes: int,
    technical_metadata: dict[str, object],
) -> tuple[MetadataField, ...]:
    fields = [
        MetadataField("checksum_sha256", checksum_sha256, "SYSTEM", confidence=1.0),
        MetadataField("mime_type", mime_type, "SYSTEM", confidence=1.0),
        MetadataField("media_type", media_type, "SYSTEM", confidence=1.0),
        MetadataField("size_bytes", size_bytes, "SYSTEM", confidence=1.0),
    ]
    for key, value in sorted(technical_metadata.items()):
        fields.append(MetadataField(key, value, "SYSTEM", confidence=1.0))
    return tuple(fields)


def user_metadata_fields(values: dict[str, object]) -> tuple[MetadataField, ...]:
    return tuple(
        MetadataField(key, value, "USER", confidence=1.0)
        for key, value in sorted(values.items())
    )
