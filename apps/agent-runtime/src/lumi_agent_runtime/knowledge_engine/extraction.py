from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import KnowledgeAccessContext, KnowledgeSegment, KnowledgeSourceRef


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionResult:
    normalized_text: str
    segments: tuple[KnowledgeSegment, ...]
    parser_version: str
    language: str | None
    used_ocr: bool

    def __post_init__(self) -> None:
        if not self.normalized_text.strip() or not self.parser_version:
            raise ValueError("KNOWLEDGE_EXTRACTION_RESULT_INVALID")


class KnowledgeExtractionPort(Protocol):
    async def extract_native(
        self,
        source: KnowledgeSourceRef,
        *,
        access: KnowledgeAccessContext,
    ) -> KnowledgeExtractionResult | None: ...

    async def extract_ocr(
        self,
        source: KnowledgeSourceRef,
        *,
        access: KnowledgeAccessContext,
    ) -> KnowledgeExtractionResult | None: ...


async def extract_native_then_ocr(
    extractor: KnowledgeExtractionPort,
    source: KnowledgeSourceRef,
    *,
    access: KnowledgeAccessContext,
) -> KnowledgeExtractionResult:
    native = await extractor.extract_native(source, access=access)
    if native is not None and native.normalized_text.strip():
        if native.used_ocr:
            raise ValueError("KNOWLEDGE_NATIVE_RESULT_CANNOT_BE_OCR")
        return native

    ocr = await extractor.extract_ocr(source, access=access)
    if ocr is None or not ocr.normalized_text.strip():
        raise ValueError("KNOWLEDGE_EXTRACTION_EMPTY")
    if not ocr.used_ocr:
        raise ValueError("KNOWLEDGE_OCR_RESULT_MARKER_REQUIRED")
    return ocr
