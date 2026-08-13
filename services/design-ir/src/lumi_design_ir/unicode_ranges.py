from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import StructuralValidationError


def codepoint_length(text: str) -> int:
    """Return Unicode code-point length (the V1 range unit)."""
    return len(text)


def validate_codepoint_spans(content: str, spans: Sequence[Mapping[str, Any]]) -> None:
    """Validate V1 rich-text ranges using Unicode code-point offsets.

    Python string indexing is code-point based, unlike JavaScript UTF-16 code-unit indexing.
    Cross-language implementations must convert JS offsets with Array.from(text).
    """
    limit = codepoint_length(content)
    previous_end = 0
    for index, span in enumerate(spans):
        start = span.get("start")
        end = span.get("end")
        if not isinstance(start, int) or isinstance(start, bool):
            raise StructuralValidationError(f"text span {index} start must be an integer")
        if not isinstance(end, int) or isinstance(end, bool):
            raise StructuralValidationError(f"text span {index} end must be an integer")
        if start < 0 or end < start or end > limit:
            raise StructuralValidationError(
                f"text span {index} [{start}, {end}) is outside code-point length {limit}"
            )
        if start < previous_end:
            raise StructuralValidationError("text spans must be ordered and non-overlapping")
        previous_end = end


def slice_codepoints(content: str, start: int, end: int) -> str:
    validate_codepoint_spans(content, ({"start": start, "end": end},))
    return content[start:end]
