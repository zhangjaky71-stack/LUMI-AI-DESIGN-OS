from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from .contracts import (
    KnowledgeAccessContext,
    KnowledgeDocument,
    KnowledgeIndexRequest,
    KnowledgeSearchQuery,
    KnowledgeSearchResult,
    KnowledgeStatus,
)
from .indexer import KnowledgeEmbeddingPort, KnowledgeIndexer
from .postgres_repository import PostgresKnowledgeRepository
from .repository import KnowledgeRepository
from .retrieval import KnowledgeRetriever


class KnowledgeService:
    """Reference service for a repository already scoped to one lifetime/transaction."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        embedder: KnowledgeEmbeddingPort | None = None,
    ) -> None:
        self.repository = repository
        self.embedder = embedder

    async def index(self, request: KnowledgeIndexRequest) -> KnowledgeDocument:
        return await KnowledgeIndexer(
            self.repository,
            embedder=self.embedder,
        ).index(request)

    async def search(
        self,
        query: KnowledgeSearchQuery,
    ) -> tuple[KnowledgeSearchResult, ...]:
        return await KnowledgeRetriever(self.repository).search(query)

    async def delete(
        self,
        document_id: UUID,
        *,
        access: KnowledgeAccessContext,
    ) -> KnowledgeDocument:
        document = await self.repository.get_document(document_id)
        _assert_manage_access(document, access)
        assert document is not None
        updated = replace(
            document,
            status=KnowledgeStatus.DELETED,
            version=document.version + 1,
        )
        return await self.repository.replace_document(
            updated,
            expected_version=document.version,
        )

    async def mark_stale(
        self,
        document_id: UUID,
        *,
        access: KnowledgeAccessContext,
    ) -> KnowledgeDocument:
        document = await self.repository.get_document(document_id)
        _assert_manage_access(document, access)
        assert document is not None
        if document.status not in {KnowledgeStatus.READY, KnowledgeStatus.STALE}:
            raise ValueError("KNOWLEDGE_STALE_STATE_INVALID")
        if document.status == KnowledgeStatus.STALE:
            return document
        updated = replace(
            document,
            status=KnowledgeStatus.STALE,
            version=document.version + 1,
        )
        return await self.repository.replace_document(
            updated,
            expected_version=document.version,
        )


class TransactionalKnowledgeService:
    def __init__(
        self,
        repository: PostgresKnowledgeRepository,
        *,
        embedder: KnowledgeEmbeddingPort | None = None,
    ) -> None:
        self.repository = repository
        self.embedder = embedder

    async def index(self, request: KnowledgeIndexRequest) -> KnowledgeDocument:
        async with self.repository.transaction() as session:
            return await KnowledgeIndexer(
                session,
                embedder=self.embedder,
            ).index(request)

    async def search(
        self,
        query: KnowledgeSearchQuery,
    ) -> tuple[KnowledgeSearchResult, ...]:
        async with self.repository.transaction() as session:
            return await KnowledgeRetriever(session).search(query)

    async def delete(
        self,
        document_id: UUID,
        *,
        access: KnowledgeAccessContext,
    ) -> KnowledgeDocument:
        async with self.repository.transaction() as session:
            return await KnowledgeService(session).delete(
                document_id,
                access=access,
            )

    async def mark_stale(
        self,
        document_id: UUID,
        *,
        access: KnowledgeAccessContext,
    ) -> KnowledgeDocument:
        async with self.repository.transaction() as session:
            return await KnowledgeService(session).mark_stale(
                document_id,
                access=access,
            )


def _assert_manage_access(
    document: KnowledgeDocument | None,
    access: KnowledgeAccessContext,
) -> None:
    if document is None or document.organization_id != access.organization_id:
        raise PermissionError("KNOWLEDGE_DOCUMENT_NOT_FOUND_OR_DENIED")
    if document.project_id is None:
        if "knowledge.organization.write" not in access.granted_permissions:
            raise PermissionError("KNOWLEDGE_ORGANIZATION_WRITE_DENIED")
    elif document.project_id != access.project_id:
        raise PermissionError("KNOWLEDGE_PROJECT_WRITE_DENIED")


def utc_now() -> datetime:
    return datetime.now(UTC)
