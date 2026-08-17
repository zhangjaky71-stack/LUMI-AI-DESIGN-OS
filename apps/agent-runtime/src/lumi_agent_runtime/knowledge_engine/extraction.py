from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from uuid import UUID

from .contracts import KnowledgeAccessContext, KnowledgeSourceType, SourceSection


@dataclass(frozen=True, slots=True)
class KnowledgeSourceInput:
    source_type: KnowledgeSourceType
    source_ref: str
    title: str
    organization_id: UUID
    permission_scope: str
    project_id: UUID | None = None
    brand_id: str | None = None
    source_updated_at: datetime | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionResult:
    sections: tuple[SourceSection, ...]
    parser_version: str
    language: str
    used_ocr: bool

    def __post_init__(self) -> None:
        if not self.sections:
            raise ValueError("KNOWLEDGE_EXTRACTION_SECTIONS_REQUIRED")
        if not self.parser_version or not self.language:
            raise ValueError("KNOWLEDGE_EXTRACTION_IDENTITY_REQUIRED")


class KnowledgeExtractionPort(Protocol):
    async def extract_native(
        self,
        source: KnowledgeSourceInput,
        *,
        access: KnowledgeAccessContext,
    ) -> KnowledgeExtractionResult | None: ...

    async def extract_ocr(
        self,
        source: KnowledgeSourceInput,
        *,
        access: KnowledgeAccessContext,
    ) -> KnowledgeExtractionResult | None: ...


async def extract_native_then_ocr(
    extractor: KnowledgeExtractionPort,
    source: KnowledgeSourceInput,
    *,
    access: KnowledgeAccessContext,
) -> KnowledgeExtractionResult:
    native = await extractor.extract_native(source, access=access)
    if native is not None:
        if native.used_ocr:
            raise ValueError("KNOWLEDGE_NATIVE_RESULT_CANNOT_BE_OCR")
        return native
    ocr = await extractor.extract_ocr(source, access=access)
    if ocr is None:
        raise ValueError("KNOWLEDGE_EXTRACTION_EMPTY")
    if not ocr.used_ocr:
        raise ValueError("KNOWLEDGE_OCR_RESULT_MARKER_REQUIRED")
    return ocr
