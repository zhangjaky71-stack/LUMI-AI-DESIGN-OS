from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ContextItem


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    item: ContextItem
    organization_id: str
    project_id: str
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    recency_score: float = 0.0
    authority_score: float = 0.0

    def __post_init__(self) -> None:
        for value in (
            self.lexical_score,
            self.semantic_score,
            self.recency_score,
            self.authority_score,
        ):
            if not 0 <= value <= 1:
                raise ValueError("CONTEXT_RETRIEVAL_SCORE_INVALID")

    @property
    def hybrid_score(self) -> float:
        return min(
            1.0,
            0.38 * self.semantic_score
            + 0.32 * self.lexical_score
            + 0.18 * self.authority_score
            + 0.12 * self.recency_score,
        )


def rank_candidates(
    candidates: tuple[RetrievalCandidate, ...],
    *,
    organization_id: str,
    project_id: str,
    limit: int,
) -> tuple[ContextItem, ...]:
    scoped = [
        candidate
        for candidate in candidates
        if candidate.organization_id == organization_id
        and candidate.project_id == project_id
    ]
    scoped.sort(
        key=lambda candidate: (
            candidate.hybrid_score,
            candidate.item.priority,
            candidate.item.source.version,
            candidate.item.item_id,
        ),
        reverse=True,
    )
    seen: set[tuple[str, str, str]] = set()
    output: list[ContextItem] = []
    for candidate in scoped:
        identity = (
            candidate.item.source.source_type,
            candidate.item.source.source_id,
            candidate.item.source.version,
        )
        if identity in seen:
            continue
        seen.add(identity)
        from dataclasses import replace

        output.append(
            replace(candidate.item, relevance_score=candidate.hybrid_score)
        )
        if len(output) >= limit:
            break
    return tuple(output)
