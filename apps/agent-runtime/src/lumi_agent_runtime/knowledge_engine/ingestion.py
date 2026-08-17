from __future__ import annotations

from .contracts import KnowledgeAccessContext, KnowledgeDocument, KnowledgeIngestRequest
from .engine import KnowledgeEngine
from .extraction import (
    KnowledgeExtractionPort,
    KnowledgeSourceInput,
    extract_native_then_ocr,
)


class KnowledgeIngestionService:
    """Source ingestion orchestrator.

    Native extraction/OCR completes before Knowledge persistence is mutated. Concrete source
    readers remain behind NODE-18 Asset/Tool/Sandbox boundaries; this service owns only the
    Knowledge transition from extracted evidence to an indexed, citation-preserving version.
    """

    def __init__(
        self,
        engine: KnowledgeEngine,
        *,
        extractor: KnowledgeExtractionPort,
    ) -> None:
        self.engine = engine
        self.extractor = extractor

    async def ingest(
        self,
        access: KnowledgeAccessContext,
        source: KnowledgeSourceInput,
    ) -> KnowledgeDocument:
        extraction = await extract_native_then_ocr(
            self.extractor,
            source,
            access=access,
        )
        return self.engine.ingest(
            access,
            KnowledgeIngestRequest(
                source_type=source.source_type,
                source_ref=source.source_ref,
                title=source.title,
                parser_version=extraction.parser_version,
                language=extraction.language,
                permission_scope=source.permission_scope,
                sections=extraction.sections,
                organization_id=source.organization_id,
                project_id=source.project_id,
                brand_id=source.brand_id,
                source_updated_at=source.source_updated_at,
                observed_at=source.observed_at,
                metadata={
                    **dict(source.metadata),
                    "used_ocr": extraction.used_ocr,
                },
            ),
        )
