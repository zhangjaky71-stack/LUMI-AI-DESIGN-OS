from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from .contracts import (
    KnowledgeCitation,
    KnowledgeSearchQuery,
    KnowledgeSearchResult,
    KnowledgeSourceType,
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
        chunks = await self.repository.list_ready_chunks(
            organization_id=query.access.organization_id
        )
        allowed_source_types = set(query.source_types)
        now = datetime.now(UTC)
        results: list[KnowledgeSearchResult] = []
        for chunk in chunks:
            if chunk.organization_id != query.access.organization_id:
                continue
            if chunk.project_id is not None:
                if query.access.project_id != chunk.project_id:
                    continue
            elif "knowledge.organization.read" not in query.access.granted_permissions:
                continue
            if (
                allowed_source_types
                and chunk.source.source_type not in allowed_source_types
            ):
                continue
            lexical = _lexical_score(query.text, chunk.text)
            semantic = _semantic_score(query.query_embedding, chunk.embedding)
            authority = _AUTHORITY[chunk.trust]
            freshness = _freshness(chunk.source.version, now)
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
        return tuple(results[: query.limit])


def _lexical_score(query: str, text: str) -> float:
    terms = {item.casefold() for item in _TOKEN.findall(query)}
    if not terms:
        return 0.0
    haystack = {item.casefold() for item in _TOKEN.findall(text)}
    return len(terms & haystack) / len(terms)


def _semantic_score(
    query: tuple[float, ...] | None,
    record: tuple[float, ...] | None,
) -> float:
    if query is None or record is None or len(query) != len(record):
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


def _freshness(version: str, now: datetime) -> float:
    del now
    # Version freshness is primarily enforced by indexing supersede semantics.
    # A ready chunk therefore gets a neutral-positive freshness score.
    return 0.75 if version else 0.0
