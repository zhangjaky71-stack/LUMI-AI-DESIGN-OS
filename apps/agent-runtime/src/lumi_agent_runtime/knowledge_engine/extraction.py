from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from uuid import UUID

from .contracts import KnowledgeAccessContext, KnowledgeSourceType, SourceSection

_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,2040}$")
_SCOPE = re.compile(r"^(project|brand|organization)(:[A-Za-z0-9_.-]+)?$")


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

    def __post_init__(self) -> None:
        if not _REF.fullmatch(self.source_ref):
            raise ValueError("KNOWLEDGE_SOURCE_REF_INVALID")
        if not self.title.strip() or len(self.title) > 1_000:
            raise ValueError("KNOWLEDGE_TITLE_INVALID")
        if not _SCOPE.fullmatch(self.permission_scope):
            raise ValueError("KNOWLEDGE_PERMISSION_SCOPE_INVALID")
        if self.permission_scope == "project" and self.project_id is None:
            raise ValueError("KNOWLEDGE_PROJECT_SCOPE_PROJECT_REQUIRED")
        if self.permission_scope.startswith("brand:"):
            expected_brand = self.permission_scope.split(":", 1)[1]
            if self.brand_id != expected_brand:
                raise ValueError("KNOWLEDGE_BRAND_SCOPE_MISMATCH")
        if self.observed_at.tzinfo is None:
            raise ValueError("KNOWLEDGE_OBSERVED_TIMEZONE_REQUIRED")
        if self.source_updated_at is not None and self.source_updated_at.tzinfo is None:
            raise ValueError("KNOWLEDGE_UPDATED_TIMEZONE_REQUIRED")


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
