from __future__ import annotations

from dataclasses import replace
from typing import Protocol
from uuid import UUID

from .contracts import KnowledgeChunk, KnowledgeDocument, KnowledgeStatus


class KnowledgeRepository(Protocol):
    async def acquire_source_lock(
        self,
        *,
        organization_id: UUID,
        scope_key: str,
        source_type: str,
        source_id: str,
    ) -> None: ...

    async def get_document(self, document_id: UUID) -> KnowledgeDocument | None: ...

    async def find_ready_source_versions(
        self,
        *,
        organization_id: UUID,
        scope_key: str,
        source_type: str,
        source_id: str,
    ) -> tuple[KnowledgeDocument, ...]: ...

    async def list_ready_chunks(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        include_organization_scope: bool,
    ) -> tuple[KnowledgeChunk, ...]: ...

    async def search_ready_chunks(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        include_organization_scope: bool,
        query_texts: tuple[str, ...],
        query_embedding: tuple[float, ...] | None,
        query_embedding_space_id: str | None,
        limit: int,
    ) -> tuple[KnowledgeChunk, ...]: ...

    async def list_chunks(
        self,
        *,
        document_id: UUID,
    ) -> tuple[KnowledgeChunk, ...]: ...

    async def insert_document(self, document: KnowledgeDocument) -> KnowledgeDocument: ...

    async def replace_document(
        self,
        document: KnowledgeDocument,
        *,
        expected_version: int,
    ) -> KnowledgeDocument: ...

    async def replace_chunks(
        self,
        document_id: UUID,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None: ...


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self._documents: dict[UUID, KnowledgeDocument] = {}
        self._chunks: dict[UUID, tuple[KnowledgeChunk, ...]] = {}

    async def acquire_source_lock(
        self,
        *,
        organization_id: UUID,
        scope_key: str,
        source_type: str,
        source_id: str,
    ) -> None:
        del organization_id, scope_key, source_type, source_id

    async def get_document(self, document_id: UUID) -> KnowledgeDocument | None:
        return self._documents.get(document_id)

    async def find_ready_source_versions(
        self,
        *,
        organization_id: UUID,
        scope_key: str,
        source_type: str,
        source_id: str,
    ) -> tuple[KnowledgeDocument, ...]:
        return tuple(
            item
            for item in self._documents.values()
            if item.organization_id == organization_id
            and item.scope_key == scope_key
            and item.source.source_type.value == source_type
            and item.source.source_id == source_id
            and item.status == KnowledgeStatus.READY
        )

    async def list_ready_chunks(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        include_organization_scope: bool,
    ) -> tuple[KnowledgeChunk, ...]:
        output: list[KnowledgeChunk] = []
        for document in self._documents.values():
            if document.organization_id != organization_id:
                continue
            if document.status != KnowledgeStatus.READY:
                continue
            if document.project_id is None:
                if not include_organization_scope:
                    continue
            elif document.project_id != project_id:
                continue
            output.extend(self._chunks.get(document.document_id, ()))
        return tuple(output)

    async def search_ready_chunks(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        include_organization_scope: bool,
        query_texts: tuple[str, ...],
        query_embedding: tuple[float, ...] | None,
        query_embedding_space_id: str | None,
        limit: int,
    ) -> tuple[KnowledgeChunk, ...]:
        del query_texts, query_embedding, query_embedding_space_id
        chunks = await self.list_ready_chunks(
            organization_id=organization_id,
            project_id=project_id,
            include_organization_scope=include_organization_scope,
        )
        return chunks[:limit]

    async def list_chunks(
        self,
        *,
        document_id: UUID,
    ) -> tuple[KnowledgeChunk, ...]:
        return self._chunks.get(document_id, ())

    async def insert_document(
        self,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument:
        if document.document_id in self._documents:
            raise ValueError("KNOWLEDGE_DOCUMENT_DUPLICATE")
        self._documents[document.document_id] = document
        return document

    async def replace_document(
        self,
        document: KnowledgeDocument,
        *,
        expected_version: int,
    ) -> KnowledgeDocument:
        current = self._documents.get(document.document_id)
        if current is None or current.version != expected_version:
            raise ValueError("KNOWLEDGE_DOCUMENT_VERSION_CONFLICT")
        if document.version != expected_version + 1:
            raise ValueError("KNOWLEDGE_DOCUMENT_VERSION_NOT_INCREMENTED")
        self._documents[document.document_id] = document
        return document

    async def replace_chunks(
        self,
        document_id: UUID,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None:
        if document_id not in self._documents:
            raise ValueError("KNOWLEDGE_DOCUMENT_NOT_FOUND")
        if any(chunk.document_id != document_id for chunk in chunks):
            raise ValueError("KNOWLEDGE_CHUNK_DOCUMENT_MISMATCH")
        self._chunks[document_id] = chunks

    async def mark_superseded(
        self,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument:
        updated = replace(
            document,
            status=KnowledgeStatus.SUPERSEDED,
            version=document.version + 1,
        )
        return await self.replace_document(
            updated,
            expected_version=document.version,
        )
