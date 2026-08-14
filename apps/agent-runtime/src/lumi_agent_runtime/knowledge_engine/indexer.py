from __future__ import annotations

from dataclasses import replace

from .chunking import chunk_document, deterministic_document_id
from .contracts import KnowledgeDocument, KnowledgeIndexRequest, KnowledgeStatus
from .repository import KnowledgeRepository


class KnowledgeIndexer:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    async def index(self, request: KnowledgeIndexRequest) -> KnowledgeDocument:
        document_id = deterministic_document_id(
            request.access.organization_id,
            source_type=request.source.source_type.value,
            source_id=request.source.source_id,
            source_version=request.source.version,
            source_hash=request.source.content_hash,
        )
        existing = await self.repository.get_document(document_id)
        if existing is not None:
            if existing.status == KnowledgeStatus.READY:
                return existing
            raise ValueError("KNOWLEDGE_DOCUMENT_IDENTITY_CONFLICT")

        current_versions = await self.repository.find_ready_source_versions(
            organization_id=request.access.organization_id,
            source_type=request.source.source_type.value,
            source_id=request.source.source_id,
        )
        document = KnowledgeDocument(
            document_id=document_id,
            organization_id=request.access.organization_id,
            project_id=request.project_id,
            source=request.source,
            trust=request.trust,
            status=KnowledgeStatus.INDEXING,
            normalized_text=request.normalized_text,
            language=request.language,
            metadata={
                **request.metadata,
                "index_request_hash": request.semantic_hash,
            },
        )
        document = await self.repository.insert_document(document)
        chunks = chunk_document(
            document,
            chunk_size_tokens=request.chunk_size_tokens,
            chunk_overlap_tokens=request.chunk_overlap_tokens,
        )
        if not chunks:
            failed = replace(
                document,
                status=KnowledgeStatus.FAILED,
                version=document.version + 1,
            )
            await self.repository.replace_document(
                failed,
                expected_version=document.version,
            )
            raise ValueError("KNOWLEDGE_DOCUMENT_NO_CHUNKS")
        await self.repository.replace_chunks(document.document_id, chunks)
        ready = replace(
            document,
            status=KnowledgeStatus.READY,
            version=document.version + 1,
        )
        ready = await self.repository.replace_document(
            ready,
            expected_version=document.version,
        )
        for old in current_versions:
            if old.document_id == ready.document_id:
                continue
            superseded = replace(
                old,
                status=KnowledgeStatus.SUPERSEDED,
                version=old.version + 1,
            )
            await self.repository.replace_document(
                superseded,
                expected_version=old.version,
            )
        return ready
