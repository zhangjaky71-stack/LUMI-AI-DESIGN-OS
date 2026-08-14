from __future__ import annotations

from dataclasses import replace
from typing import Protocol
from uuid import UUID

from .chunking import chunk_document, deterministic_document_id
from .contracts import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndexRequest,
    KnowledgeStatus,
)
from .repository import KnowledgeRepository


class KnowledgeEmbeddingPort(Protocol):
    async def embed(
        self,
        chunks: tuple[KnowledgeChunk, ...],
        *,
        embedding_space_id: str,
    ) -> tuple[KnowledgeChunk, ...]: ...


class KnowledgeIndexer:
    """Indexes one extracted source using a repository transaction/lifetime."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        embedder: KnowledgeEmbeddingPort | None = None,
    ) -> None:
        self.repository = repository
        self.embedder = embedder

    async def index(self, request: KnowledgeIndexRequest) -> KnowledgeDocument:
        await self.repository.acquire_source_lock(
            organization_id=request.access.organization_id,
            scope_key=request.scope_key,
            source_type=request.source.source_type.value,
            source_id=request.source.source_id,
        )
        document_id = deterministic_document_id(
            request.access.organization_id,
            scope_key=request.scope_key,
            source_type=request.source.source_type.value,
            source_id=request.source.source_id,
            source_version=request.source.version,
            source_hash=request.source.content_hash,
            index_version=request.index_version,
        )
        existing = await self.repository.get_document(document_id)
        if existing is not None:
            if existing.status == KnowledgeStatus.READY:
                if existing.metadata.get("index_request_hash") != request.semantic_hash:
                    raise ValueError("KNOWLEDGE_INDEX_VERSION_CONFIGURATION_CONFLICT")
                return existing
            if existing.status in {
                KnowledgeStatus.PENDING,
                KnowledgeStatus.EXTRACTING,
                KnowledgeStatus.FAILED,
            }:
                document = await self._prepare_existing(existing, request)
            else:
                raise ValueError("KNOWLEDGE_DOCUMENT_IDENTITY_CONFLICT")
        else:
            document = KnowledgeDocument(
                document_id=document_id,
                organization_id=request.access.organization_id,
                project_id=request.project_id,
                source=request.source,
                permission_scope=request.permission_scope,
                trust=request.trust,
                status=KnowledgeStatus.PENDING,
                normalized_text=request.normalized_text,
                parser_version=request.parser_version,
                chunker_version=request.chunker_version,
                index_version=request.index_version,
                language=request.language,
                embedding_space_id=request.embedding_space_id,
                metadata={
                    **request.metadata,
                    "index_request_hash": request.semantic_hash,
                },
            )
            document = await self.repository.insert_document(document)

        current_versions = await self.repository.find_ready_source_versions(
            organization_id=request.access.organization_id,
            scope_key=request.scope_key,
            source_type=request.source.source_type.value,
            source_id=request.source.source_id,
        )
        document = await self._transition(document, KnowledgeStatus.CHUNKING)

        chunks = chunk_document(
            document,
            chunk_size_tokens=request.chunk_size_tokens,
            chunk_overlap_tokens=request.chunk_overlap_tokens,
            segments=request.segments,
        )
        if not chunks:
            await self._transition(document, KnowledgeStatus.FAILED)
            raise ValueError("KNOWLEDGE_DOCUMENT_NO_CHUNKS")

        if request.embedding_space_id is not None:
            if self.embedder is None:
                await self._transition(document, KnowledgeStatus.FAILED)
                raise ValueError("KNOWLEDGE_EMBEDDER_REQUIRED")
            document = await self._transition(document, KnowledgeStatus.EMBEDDING)
            chunks = await self.embedder.embed(
                chunks,
                embedding_space_id=request.embedding_space_id,
            )
            _validate_embedded_chunks(
                chunks,
                document_id=document.document_id,
                embedding_space_id=request.embedding_space_id,
            )

        await self.repository.replace_chunks(document.document_id, chunks)
        ready = await self._transition(document, KnowledgeStatus.READY)

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

    async def _prepare_existing(
        self,
        document: KnowledgeDocument,
        request: KnowledgeIndexRequest,
    ) -> KnowledgeDocument:
        expected_ingest_hash = document.metadata.get("ingest_config_hash")
        provided_ingest_hash = request.metadata.get("ingest_config_hash")
        if expected_ingest_hash is not None and expected_ingest_hash != provided_ingest_hash:
            raise ValueError("KNOWLEDGE_INGEST_CONFIGURATION_CONFLICT")
        prepared = replace(
            document,
            project_id=request.project_id,
            permission_scope=request.permission_scope,
            trust=request.trust,
            normalized_text=request.normalized_text,
            parser_version=request.parser_version,
            chunker_version=request.chunker_version,
            index_version=request.index_version,
            language=request.language,
            embedding_space_id=request.embedding_space_id,
            metadata={
                **request.metadata,
                "index_request_hash": request.semantic_hash,
            },
            version=document.version + 1,
        )
        return await self.repository.replace_document(
            prepared,
            expected_version=document.version,
        )

    async def _transition(
        self,
        document: KnowledgeDocument,
        status: KnowledgeStatus,
    ) -> KnowledgeDocument:
        updated = replace(
            document,
            status=status,
            version=document.version + 1,
        )
        return await self.repository.replace_document(
            updated,
            expected_version=document.version,
        )


def _validate_embedded_chunks(
    chunks: tuple[KnowledgeChunk, ...],
    *,
    document_id: UUID,
    embedding_space_id: str,
) -> None:
    if not chunks:
        raise ValueError("KNOWLEDGE_EMBEDDER_RETURNED_EMPTY")
    for chunk in chunks:
        if chunk.document_id != document_id:
            raise ValueError("KNOWLEDGE_EMBEDDER_DOCUMENT_MISMATCH")
        if chunk.embedding is None or chunk.embedding_space_id != embedding_space_id:
            raise ValueError("KNOWLEDGE_EMBEDDER_SPACE_MISMATCH")
