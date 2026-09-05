from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from .chunking import deterministic_document_id
from .contracts import (
    KnowledgeDocument,
    KnowledgeIndexRequest,
    KnowledgeIngestRequest,
    KnowledgeStatus,
)
from .extraction import KnowledgeExtractionPort, extract_native_then_ocr
from .indexer import KnowledgeEmbeddingPort
from .postgres_repository import PostgresKnowledgeRepository
from .service import TransactionalKnowledgeService


class TransactionalKnowledgeIngestionService:
    """Durable native-first ingestion without holding DB transactions over extraction."""

    def __init__(
        self,
        repository: PostgresKnowledgeRepository,
        *,
        extractor: KnowledgeExtractionPort,
        embedder: KnowledgeEmbeddingPort | None = None,
    ) -> None:
        self.repository = repository
        self.extractor = extractor
        self.embedder = embedder

    async def ingest(self, request: KnowledgeIngestRequest) -> KnowledgeDocument:
        begun = await self._begin_extraction(request)
        if begun.status == KnowledgeStatus.READY:
            return begun

        try:
            extraction = await extract_native_then_ocr(
                self.extractor,
                request.source,
                access=request.access,
            )
        except Exception:
            await self._mark_failed(
                begun.document_id,
                failure_code="KNOWLEDGE_EXTRACTION_FAILED",
            )
            raise

        index_request = KnowledgeIndexRequest(
            access=request.access,
            source=request.source,
            trust=request.trust,
            normalized_text=extraction.normalized_text,
            project_id=request.project_id,
            permission_scope=request.permission_scope,
            language=extraction.language,
            parser_version=extraction.parser_version,
            chunker_version=request.chunker_version,
            index_version=request.index_version,
            embedding_space_id=request.embedding_space_id,
            chunk_size_tokens=request.chunk_size_tokens,
            chunk_overlap_tokens=request.chunk_overlap_tokens,
            segments=extraction.segments,
            metadata={
                **request.metadata,
                "ingest_config_hash": request.config_hash,
                "used_ocr": extraction.used_ocr,
            },
        )
        try:
            return await TransactionalKnowledgeService(
                self.repository,
                embedder=self.embedder,
            ).index(index_request)
        except Exception:
            await self._mark_failed(
                begun.document_id,
                failure_code="KNOWLEDGE_INDEX_FINALIZE_FAILED",
            )
            raise

    async def _begin_extraction(
        self,
        request: KnowledgeIngestRequest,
    ) -> KnowledgeDocument:
        document_id = _document_id(request)
        async with self.repository.transaction() as session:
            await session.acquire_source_lock(
                organization_id=request.access.organization_id,
                scope_key=request.scope_key,
                source_type=request.source.source_type.value,
                source_id=request.source.source_id,
            )
            existing = await session.get_document(document_id)
            if existing is not None:
                stored_hash = existing.metadata.get("ingest_config_hash")
                if stored_hash != request.config_hash:
                    raise ValueError("KNOWLEDGE_INGEST_CONFIGURATION_CONFLICT")
                if existing.status == KnowledgeStatus.READY:
                    return existing
                if existing.status not in {
                    KnowledgeStatus.PENDING,
                    KnowledgeStatus.EXTRACTING,
                    KnowledgeStatus.FAILED,
                }:
                    raise ValueError("KNOWLEDGE_INGEST_STATE_CONFLICT")
                extracting = replace(
                    existing,
                    status=KnowledgeStatus.EXTRACTING,
                    metadata={
                        **existing.metadata,
                        "failure_code": None,
                    },
                    version=existing.version + 1,
                )
                return await session.replace_document(
                    extracting,
                    expected_version=existing.version,
                )

            pending = KnowledgeDocument(
                document_id=document_id,
                organization_id=request.access.organization_id,
                project_id=request.project_id,
                source=request.source,
                permission_scope=request.permission_scope,
                trust=request.trust,
                status=KnowledgeStatus.PENDING,
                normalized_text="",
                parser_version="pending",
                chunker_version=request.chunker_version,
                index_version=request.index_version,
                embedding_space_id=request.embedding_space_id,
                metadata={
                    **request.metadata,
                    "ingest_config_hash": request.config_hash,
                },
            )
            pending = await session.insert_document(pending)
            extracting = replace(
                pending,
                status=KnowledgeStatus.EXTRACTING,
                version=pending.version + 1,
            )
            return await session.replace_document(
                extracting,
                expected_version=pending.version,
            )

    async def _mark_failed(
        self,
        document_id: UUID,
        *,
        failure_code: str,
    ) -> None:
        async with self.repository.transaction() as session:
            document = await session.get_document(document_id)
            if document is None:
                return
            if document.status in {
                KnowledgeStatus.READY,
                KnowledgeStatus.SUPERSEDED,
                KnowledgeStatus.DELETED,
                KnowledgeStatus.STALE,
            }:
                return
            failed = replace(
                document,
                status=KnowledgeStatus.FAILED,
                metadata={
                    **document.metadata,
                    "failure_code": failure_code,
                },
                version=document.version + 1,
            )
            await session.replace_document(
                failed,
                expected_version=document.version,
            )


def _document_id(request: KnowledgeIngestRequest) -> UUID:
    return deterministic_document_id(
        request.access.organization_id,
        scope_key=request.scope_key,
        source_type=request.source.source_type.value,
        source_id=request.source.source_id,
        source_version=request.source.version,
        source_hash=request.source.content_hash,
        index_version=request.index_version,
    )
