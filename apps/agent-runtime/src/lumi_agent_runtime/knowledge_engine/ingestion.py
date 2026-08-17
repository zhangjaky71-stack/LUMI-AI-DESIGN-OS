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

    Authorization completes before a trusted source adapter performs any source I/O. Native
    extraction/OCR then completes before Knowledge persistence is mutated. Concrete source readers
    remain behind NODE-18 Asset/Tool/Sandbox boundaries.
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
        _authorize_source(access, source)
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


def _authorize_source(
    access: KnowledgeAccessContext,
    source: KnowledgeSourceInput,
) -> None:
    if source.organization_id != access.organization_id:
        raise PermissionError("KNOWLEDGE_TENANT_DENIED")
    if source.project_id is not None and source.project_id != access.project_id:
        raise PermissionError("KNOWLEDGE_PROJECT_DENIED")
    if source.brand_id is not None and source.brand_id not in access.brand_ids:
        raise PermissionError("KNOWLEDGE_BRAND_DENIED")
    if not access.allows(source.permission_scope):
        raise PermissionError("KNOWLEDGE_SCOPE_DENIED")
