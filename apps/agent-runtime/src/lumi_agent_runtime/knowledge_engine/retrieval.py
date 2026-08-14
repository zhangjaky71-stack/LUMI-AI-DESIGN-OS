from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import UTC, datetime

from .contracts import (
    KnowledgeCitation,
    KnowledgeSearchQuery,
    KnowledgeSearchResult,
    KnowledgeTrust,
)
from .repository import KnowledgeRepository

_TOKEN = re.compile(r"[\w-]+", re.UNICODE)
_AUTHORITY = {
    KnowledgeTrust.INTERNAL_DATA: 0.90,
    KnowledgeTrust.USER_CONTENT: 0.72,
    KnowledgeTrust.EXTERNAL_UNTRUSTED: 0.45,
    KnowledgeTrust.MODEL_GENERATED: 0.30,
}


class KnowledgeRetriever:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    async def search(
        self,
        query: KnowledgeSearchQuery,
    ) -> tuple[KnowledgeSearchResult, ...]:
        include_organization_scope = (
            "knowledge.organization.read" in query.access.granted_permissions
        )
        candidate_limit = min(400, max(64, query.limit * 10))
        chunks = await self.repository.search_ready_chunks(
            organization_id=query.access.organization_id,
            project_id=query.access.project_id,
            include_organization_scope=include_organization_scope,
            query_texts=(query.text, *query.expanded_queries),
            query_embedding=query.query_embedding,
            query_embedding_space_id=query.query_embedding_space_id,
            limit=candidate_limit,
        )
        allowed_source_types = set(query.source_types)
        now = query.now or datetime.now(UTC)
        results: list[KnowledgeSearchResult] = []
        for chunk in chunks:
            # Defense in depth. Durable candidate retrieval must already have
            # applied the same organization/project permission boundary.
            if chunk.organization_id != query.access.organization_id:
                continue
            if chunk.project_id is not None:
                if query.access.project_id != chunk.project_id:
                    continue
            elif not include_organization_scope:
                continue
            if allowed_source_types and chunk.source.source_type not in allowed_source_types:
                continue

            stale, freshness = _freshness(
                chunk.source.source_updated_at or chunk.source.observed_at,
                now,
                max_age_seconds=query.max_source_age_seconds,
            )
            if query.require_fresh and stale:
                continue

            lexical = max(
                _lexical_score(text, chunk.text)
                for text in (query.text, *query.expanded_queries)
            )
            semantic = _semantic_score(
                query.query_embedding,
                chunk.embedding,
                query_space=query.query_embedding_space_id,
                chunk_space=chunk.embedding_space_id,
            )
            authority = _AUTHORITY[chunk.trust]
            score = min(
                1.0,
                0.38 * semantic
                + 0.34 * lexical
                + 0.18 * authority
                + 0.10 * freshness,
            )
            citation = KnowledgeCitation(
                source_type=chunk.source.source_type.value,
                source_id=chunk.source.source_id,
                source_version=chunk.source.version,
                source_hash=chunk.source.content_hash,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                locator=chunk.locator,
                title=chunk.source.title,
                uri=chunk.source.uri,
            )
            results.append(
                KnowledgeSearchResult(
                    chunk=chunk,
                    score=score,
                    lexical_score=lexical,
                    semantic_score=semantic,
                    freshness_score=freshness,
                    authority_score=authority,
                    citation=citation,
                    stale=stale,
                )
            )

        results.sort(
            key=lambda item: (
                item.score,
                item.authority_score,
                item.chunk.source.version,
                str(item.chunk.chunk_id),
            ),
            reverse=True,
        )
        return _diversify(results, limit=query.limit)


def _lexical_score(query: str, text: str) -> float:
    terms = {item.casefold() for item in _TOKEN.findall(query)}
    if not terms:
        return 0.0
    haystack = {item.casefold() for item in _TOKEN.findall(text)}
    return len(terms & haystack) / len(terms)


def _semantic_score(
    query: tuple[float, ...] | None,
    record: tuple[float, ...] | None,
    *,
    query_space: str | None,
    chunk_space: str | None,
) -> float:
    if query is None or record is None:
        return 0.0
    if query_space is None or query_space != chunk_space:
        return 0.0
    if len(query) != len(record):
        return 0.0
    dot = sum(a * b for a, b in zip(query, record, strict=True))
    left = math.sqrt(sum(value * value for value in query))
    right = math.sqrt(sum(value * value for value in record))
    if left == 0 or right == 0:
        return 0.0
    return max(
        0.0,
        min(1.0, (dot / (left * right) + 1.0) / 2.0),
    )


def _freshness(
    source_time: datetime | None,
    now: datetime,
    *,
    max_age_seconds: int | None,
) -> tuple[bool, float]:
    if source_time is None:
        return (max_age_seconds is not None, 0.35)
    if source_time.tzinfo is None:
        source_time = source_time.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    age_seconds = max(0.0, (now - source_time).total_seconds())
    stale = max_age_seconds is not None and age_seconds > max_age_seconds
    age_days = age_seconds / 86400
    freshness = 1.0 / (1.0 + age_days / 30.0)
    return stale, freshness


def _diversify(
    ranked: list[KnowledgeSearchResult],
    *,
    limit: int,
) -> tuple[KnowledgeSearchResult, ...]:
    per_document: dict[object, int] = defaultdict(int)
    selected: list[KnowledgeSearchResult] = []
    seen_chunks: set[object] = set()
    for result in ranked:
        if result.chunk.chunk_id in seen_chunks:
            continue
        if per_document[result.chunk.document_id] >= 2:
            continue
        seen_chunks.add(result.chunk.chunk_id)
        per_document[result.chunk.document_id] += 1
        selected.append(result)
        if len(selected) >= limit:
            break
    return tuple(selected)
