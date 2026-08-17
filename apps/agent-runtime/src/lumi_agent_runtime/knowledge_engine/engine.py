from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Iterable

from .contracts import (
    IngestionState,
    KnowledgeAccessContext,
    KnowledgeChunk,
    KnowledgeCitation,
    KnowledgeDocument,
    KnowledgeHit,
    KnowledgeIngestRequest,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    cosine_similarity,
    document_content_hash,
    stable_hash,
    tokenize,
)
from .store import InMemoryKnowledgeStore


class DeterministicEmbedding:
    """Dependency-free reference embedder; production adapters replace this space."""

    def __init__(self, *, version: str = "deterministic-64-v1", dimensions: int = 64) -> None:
        if dimensions < 8:
            raise ValueError("KNOWLEDGE_EMBEDDING_DIMENSION_INVALID")
        self.version = version
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = int(stable_hash(token)[:16], 16)
            index = digest % self.dimensions
            sign = -1.0 if (digest >> 8) & 1 else 1.0
            values[index] += sign
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return tuple(value / norm for value in values)


class KnowledgeEngine:
    def __init__(
        self,
        store: InMemoryKnowledgeStore | None = None,
        embedder: DeterministicEmbedding | None = None,
        *,
        chunker_version: str = "structure-window-v1",
        chunk_tokens: int = 220,
        overlap_tokens: int = 40,
        stale_after_seconds: int = 86_400 * 30,
    ) -> None:
        if not 32 <= chunk_tokens <= 4_000:
            raise ValueError("KNOWLEDGE_CHUNK_WINDOW_INVALID")
        if not 0 <= overlap_tokens < chunk_tokens:
            raise ValueError("KNOWLEDGE_CHUNK_OVERLAP_INVALID")
        self.store = store or InMemoryKnowledgeStore()
        self.embedder = embedder or DeterministicEmbedding()
        self.chunker_version = chunker_version
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = overlap_tokens
        self.stale_after_seconds = stale_after_seconds

    def ingest(
        self,
        access: KnowledgeAccessContext,
        request: KnowledgeIngestRequest,
        *,
        now: datetime | None = None,
    ) -> KnowledgeDocument:
        self._authorize_ingest(access, request)
        timestamp = now or datetime.now(timezone.utc)
        content_hash = document_content_hash(request)
        document_id = f"kdoc_{stable_hash([str(request.organization_id), request.source_ref])[:24]}"
        index_version = _index_version(
            request.parser_version,
            self.chunker_version,
            self.embedder.version,
        )
        document = KnowledgeDocument(
            document_id=document_id,
            organization_id=request.organization_id,
            project_id=request.project_id,
            brand_id=request.brand_id,
            source_type=request.source_type,
            source_ref=request.source_ref,
            title=request.title,
            content_hash=content_hash,
            parser_version=request.parser_version,
            chunker_version=self.chunker_version,
            embedding_version=self.embedder.version,
            index_version=index_version,
            language=request.language,
            permission_scope=request.permission_scope,
            state=IngestionState.READY,
            created_at=timestamp,
            observed_at=request.observed_at,
            source_updated_at=request.source_updated_at,
            metadata=request.metadata,
        )
        chunks = self._build_chunks(document, request)
        self.store.put_document(document, chunks)
        return document

    def search(
        self,
        access: KnowledgeAccessContext,
        request: KnowledgeSearchRequest,
        *,
        now: datetime | None = None,
    ) -> KnowledgeSearchResult:
        effective_scopes = tuple(
            scope for scope in request.permission_scopes if access.allows(scope)
        )
        query_text = " ".join((request.query, *request.query_expansions))
        query_tokens = tokenize(query_text)
        query_embedding = self.embedder.embed(query_text)
        timestamp = now or datetime.now(timezone.utc)
        ranked: list[KnowledgeHit] = []
        index_versions: set[str] = set()

        # Tenant/project/brand/scope filtering happens before any scoring.
        for document, chunk in self.store.visible_candidates(access, effective_scopes):
            index_versions.add(chunk.index_version)
            stale = self._is_stale(document, timestamp)
            if stale and not request.include_stale:
                continue
            lexical = _lexical_score(query_tokens, tokenize(chunk.text))
            vector = (cosine_similarity(query_embedding, chunk.embedding) + 1.0) / 2.0
            fusion = min(1.0, 0.62 * lexical + 0.38 * vector)
            freshness = 0.35 if stale else 1.0
            ranked.append(
                KnowledgeHit(
                    chunk=chunk,
                    document=document,
                    citation=KnowledgeCitation(
                        document_id=document.document_id,
                        chunk_id=chunk.chunk_id,
                        source_ref=document.source_ref,
                        title=document.title,
                        page=chunk.page,
                        section=chunk.section,
                        content_hash=chunk.content_hash,
                    ),
                    lexical_score=lexical,
                    vector_score=vector,
                    fusion_score=fusion,
                    freshness_score=freshness,
                    stale=stale,
                )
            )

        ranked.sort(
            key=lambda hit: (
                hit.rank_score,
                hit.fusion_score,
                hit.lexical_score,
                hit.chunk.content_hash,
            ),
            reverse=True,
        )
        diversified: list[KnowledgeHit] = []
        per_document: dict[str, int] = defaultdict(int)
        seen_hashes: set[str] = set()
        for hit in ranked:
            if hit.chunk.content_hash in seen_hashes:
                continue
            if per_document[hit.document.document_id] >= request.max_chunks_per_document:
                continue
            seen_hashes.add(hit.chunk.content_hash)
            per_document[hit.document.document_id] += 1
            diversified.append(hit)
            if len(diversified) >= request.limit:
                break

        warnings: list[str] = []
        if any(hit.stale for hit in diversified):
            warnings.append("KNOWLEDGE_STALE_SOURCE_PRESENT")
        return KnowledgeSearchResult(
            original_query=request.query,
            query_expansions=request.query_expansions,
            hits=tuple(diversified),
            searched_index_versions=tuple(sorted(index_versions)),
            warnings=tuple(warnings),
        )

    def reindex(
        self,
        access: KnowledgeAccessContext,
        document_id: str,
        request: KnowledgeIngestRequest,
        *,
        embedder: DeterministicEmbedding,
        now: datetime | None = None,
    ) -> KnowledgeDocument:
        previous = self.store.get_document(document_id)
        if previous is None:
            raise KeyError("KNOWLEDGE_DOCUMENT_NOT_FOUND")
        if previous.organization_id != access.organization_id:
            raise PermissionError("KNOWLEDGE_TENANT_DENIED")
        old_embedder = self.embedder
        try:
            self.embedder = embedder
            rebuilt = self.ingest(access, request, now=now)
        finally:
            self.embedder = old_embedder
        if rebuilt.index_version == previous.index_version:
            raise ValueError("KNOWLEDGE_REINDEX_VERSION_UNCHANGED")
        return rebuilt

    def delete_document(
        self,
        access: KnowledgeAccessContext,
        document_id: str,
    ) -> None:
        document = self.store.get_document(document_id)
        if document is None:
            raise KeyError("KNOWLEDGE_DOCUMENT_NOT_FOUND")
        if document.organization_id != access.organization_id:
            raise PermissionError("KNOWLEDGE_TENANT_DENIED")
        if document.project_id is not None and document.project_id != access.project_id:
            raise PermissionError("KNOWLEDGE_PROJECT_DENIED")
        self.store.mark_deleted(document_id)

    def _authorize_ingest(
        self,
        access: KnowledgeAccessContext,
        request: KnowledgeIngestRequest,
    ) -> None:
        if request.organization_id != access.organization_id:
            raise PermissionError("KNOWLEDGE_TENANT_DENIED")
        if request.project_id is not None and request.project_id != access.project_id:
            raise PermissionError("KNOWLEDGE_PROJECT_DENIED")
        if request.brand_id is not None and request.brand_id not in access.brand_ids:
            raise PermissionError("KNOWLEDGE_BRAND_DENIED")
        if not access.allows(request.permission_scope):
            raise PermissionError("KNOWLEDGE_SCOPE_DENIED")

    def _build_chunks(
        self,
        document: KnowledgeDocument,
        request: KnowledgeIngestRequest,
    ) -> tuple[KnowledgeChunk, ...]:
        output: list[KnowledgeChunk] = []
        ordinal = 0
        for source in request.sections:
            words = source.text.split()
            if not words:
                continue
            step = self.chunk_tokens - self.overlap_tokens
            for start in range(0, len(words), step):
                text = " ".join(words[start : start + self.chunk_tokens]).strip()
                if not text:
                    continue
                content_hash = stable_hash(
                    {
                        "document_hash": document.content_hash,
                        "page": source.page,
                        "section": source.section,
                        "ordinal": ordinal,
                        "text": text,
                    }
                )
                output.append(
                    KnowledgeChunk(
                        chunk_id=f"kchunk_{content_hash[:24]}",
                        document_id=document.document_id,
                        ordinal=ordinal,
                        text=text,
                        page=source.page,
                        section=source.section,
                        token_count=max(1, len(tokenize(text))),
                        content_hash=content_hash,
                        embedding=self.embedder.embed(text),
                        index_version=document.index_version,
                        metadata={"source_ordinal": ordinal},
                    )
                )
                ordinal += 1
                if start + self.chunk_tokens >= len(words):
                    break
        if not output:
            raise ValueError("KNOWLEDGE_NO_CHUNKS")
        return tuple(output)

    def _is_stale(self, document: KnowledgeDocument, now: datetime) -> bool:
        anchor = document.source_updated_at or document.observed_at
        return (now - anchor).total_seconds() > self.stale_after_seconds


def _index_version(parser: str, chunker: str, embedding: str) -> str:
    digest = stable_hash([parser, chunker, embedding])[:16]
    return f"idx-{digest}"


def _lexical_score(query: Iterable[str], document: Iterable[str]) -> float:
    query_counter = Counter(query)
    doc_counter = Counter(document)
    if not query_counter or not doc_counter:
        return 0.0
    overlap = sum(min(count, doc_counter.get(term, 0)) for term, count in query_counter.items())
    return min(1.0, overlap / max(1, sum(query_counter.values())))
