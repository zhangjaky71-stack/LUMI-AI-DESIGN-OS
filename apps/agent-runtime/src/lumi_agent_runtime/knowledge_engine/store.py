from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from .contracts import (
    IngestionState,
    KnowledgeAccessContext,
    KnowledgeChunk,
    KnowledgeDocument,
)


class InMemoryKnowledgeStore:
    """Reference store. Visibility filtering happens here, before scoring."""

    def __init__(self) -> None:
        self._documents: dict[str, KnowledgeDocument] = {}
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._by_document: dict[str, list[str]] = defaultdict(list)

    def put_document(
        self,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None:
        if any(chunk.document_id != document.document_id for chunk in chunks):
            raise ValueError("KNOWLEDGE_CHUNK_DOCUMENT_MISMATCH")
        old_ids = self._by_document.get(document.document_id, [])
        for chunk_id in old_ids:
            self._chunks.pop(chunk_id, None)
        self._documents[document.document_id] = document
        self._by_document[document.document_id] = []
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk
            self._by_document[document.document_id].append(chunk.chunk_id)

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        return self._documents.get(document_id)

    def get_chunks(self, document_id: str) -> tuple[KnowledgeChunk, ...]:
        return tuple(
            self._chunks[chunk_id]
            for chunk_id in self._by_document.get(document_id, ())
            if chunk_id in self._chunks
        )

    def visible_candidates(
        self,
        access: KnowledgeAccessContext,
        permission_scopes: tuple[str, ...],
    ) -> Iterable[tuple[KnowledgeDocument, KnowledgeChunk]]:
        requested = tuple(scope for scope in permission_scopes if access.allows(scope))
        for document in self._documents.values():
            if document.organization_id != access.organization_id:
                continue
            if document.project_id is not None and document.project_id != access.project_id:
                continue
            if document.brand_id is not None and document.brand_id not in access.brand_ids:
                continue
            if document.permission_scope not in requested and not any(
                _scope_allows(scope, document.permission_scope) for scope in requested
            ):
                continue
            if document.state in {IngestionState.FAILED, IngestionState.DELETED}:
                continue
            for chunk in self.get_chunks(document.document_id):
                yield document, chunk

    def mark_deleted(self, document_id: str) -> None:
        document = self._documents.get(document_id)
        if document is None:
            raise KeyError("KNOWLEDGE_DOCUMENT_NOT_FOUND")
        self._documents[document_id] = replace(document, state=IngestionState.DELETED)
        for chunk_id in self._by_document.pop(document_id, []):
            self._chunks.pop(chunk_id, None)


def _scope_allows(granted: str, requested: str) -> bool:
    return granted == requested or granted == requested.split(":", 1)[0]
