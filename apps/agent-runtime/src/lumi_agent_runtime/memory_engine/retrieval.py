from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from .contracts import MemoryScope, MemorySearchQuery, MemorySearchResult
from .policy import can_read_scope
from .repository import MemoryRepository

_TOKEN = re.compile(r"[\w-]+", re.UNICODE)
_SCOPE_WEIGHT = {
    MemoryScope.SESSION: 1.00,
    MemoryScope.PROJECT: 0.98,
    MemoryScope.BRAND: 0.90,
    MemoryScope.USER: 0.78,
    MemoryScope.AGENT: 0.62,
    MemoryScope.ORGANIZATION: 0.50,
}


class MemoryRetriever:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    async def search(
        self,
        query: MemorySearchQuery,
    ) -> tuple[MemorySearchResult, ...]:
        records = await self.repository.list_active(
            organization_id=query.access.organization_id
        )
        requested_scopes = set(query.scope_types)
        now = datetime.now(UTC)
        results: list[MemorySearchResult] = []
        for record in records:
            if requested_scopes and record.scope_type not in requested_scopes:
                continue
            if query.kind is not None and record.kind != query.kind:
                continue
            if not can_read_scope(
                record.scope_type,
                record.scope_id,
                query.access,
            ):
                continue
            lexical = _lexical_score(
                query.text,
                f"{record.semantic_key} {record.summary}",
            )
            semantic = _semantic_score(
                query.query_embedding,
                record.embedding,
            )
            scope_score = _SCOPE_WEIGHT[record.scope_type]
            confidence = record.confidence
            freshness = _freshness(
                record.last_confirmed_at or record.created_at,
                now,
            )
            score = min(
                1.0,
                0.30 * lexical
                + 0.28 * semantic
                + 0.20 * scope_score
                + 0.14 * confidence
                + 0.08 * freshness,
            )
            results.append(
                MemorySearchResult(
                    record=record,
                    score=score,
                    lexical_score=lexical,
                    semantic_score=semantic,
                    scope_score=scope_score,
                    confidence_score=confidence,
                    freshness_score=freshness,
                )
            )
        results.sort(
            key=lambda item: (
                item.score,
                item.record.confidence,
                item.record.version,
                str(item.record.memory_id),
            ),
            reverse=True,
        )
        return tuple(results[: query.limit])


def _lexical_score(query: str, text: str) -> float:
    terms = {token.casefold() for token in _TOKEN.findall(query)}
    if not terms:
        return 0.0
    haystack = {token.casefold() for token in _TOKEN.findall(text)}
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


def _freshness(value: datetime, now: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    age_days = max(0.0, (now - value).total_seconds() / 86400)
    return 1.0 / (1.0 + age_days / 30.0)
