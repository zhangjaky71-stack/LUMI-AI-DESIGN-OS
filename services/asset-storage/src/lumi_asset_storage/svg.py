from __future__ import annotations

import re
import xml.etree.ElementTree as ET

_DANGEROUS_TEXT = re.compile(
    r"(?:javascript\s*:|@import|expression\s*\(|url\s*\(\s*['\"]?(?:https?:|//|data:))",
    flags=re.IGNORECASE,
)


def sanitize_svg(data: bytes, *, max_bytes: int = 5_000_000) -> bytes:
    if len(data) > max_bytes:
        raise ValueError("SVG_TOO_LARGE")
    if b"\x00" in data:
        raise ValueError("SVG_INVALID_BINARY")
    text = data.decode("utf-8-sig", errors="strict")
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("SVG_DTD_OR_ENTITY_REJECTED")
    if _DANGEROUS_TEXT.search(text):
        raise ValueError("SVG_DANGEROUS_REFERENCE")

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("SVG_XML_INVALID") from exc
    if _local_name(root.tag) != "svg":
        raise ValueError("SVG_ROOT_REQUIRED")

    for element in root.iter():
        tag = _local_name(element.tag).lower()
        if tag in {"script", "foreignobject", "iframe", "object", "embed"}:
            raise ValueError("SVG_ACTIVE_CONTENT_REJECTED")
        for name, value in element.attrib.items():
            local = _local_name(name).lower()
            lowered_value = value.strip().lower()
            if local.startswith("on"):
                raise ValueError("SVG_EVENT_HANDLER_REJECTED")
            if local in {"href", "src"}:
                if lowered_value and not lowered_value.startswith("#"):
                    raise ValueError("SVG_EXTERNAL_REFERENCE_REJECTED")
            if local == "style" and _DANGEROUS_TEXT.search(value):
                raise ValueError("SVG_DANGEROUS_STYLE")

    cleaned = ET.tostring(root, encoding="utf-8", method="xml")
    if b"<!DOCTYPE" in cleaned or b"<!ENTITY" in cleaned:
        raise ValueError("SVG_SANITIZER_FAILED")
    return cleaned


def _local_name(value: str) -> str:
    if "}" in value:
        return value.rsplit("}", 1)[1]
    if ":" in value:
        return value.rsplit(":", 1)[1]
    return value
