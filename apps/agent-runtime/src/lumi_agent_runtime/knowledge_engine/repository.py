from __future__ import annotations

from dataclasses import replace
from typing import Protocol
from uuid import UUID

from .contracts import KnowledgeChunk, KnowledgeDocument, KnowledgeStatus


class KnowledgeRepository(Protocol):
    async def get_document(self, document_id: UUID) -> KnowledgeDocument | None: ...

    async def find_ready_source_versions(
        self,
        *,
        organization_id: UUID,
        source_type: str,
        source_id: str,
    ) -> tuple[KnowledgeDocument, ...]: ...

    async def list_ready_chunks(
        self,
        *,
        organization_id: UUID,
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

    async def get_document(self, document_id: UUID) -> KnowledgeDocument | None:
        return self._documents.get(document_id)

    async def find_ready_source_versions(
        self,
        *,
        organization_id: UUID,
        source_type: str,
        source_id: str,
    ) -> tuple[KnowledgeDocument, ...]:
        return tuple(
            item
            for item in self._documents.values()
            if item.organization_id == organization_id
            and item.source.source_type.value == source_type
            and item.source.source_id == source_id
            and item.status == KnowledgeStatus.READY
        )

    async def list_ready_chunks(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[KnowledgeChunk, ...]:
        output: list[KnowledgeChunk] = []
        for document in self._documents.values():
            if (
                document.organization_id == organization_id
                and document.status == KnowledgeStatus.READY
            ):
                output.extend(self._chunks.get(document.document_id, ()))
        return tuple(output)

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
