from __future__ import annotations

from dataclasses import dataclass, replace

from .contracts import ContextItem, ContextKind, ContextLayer, ContextRequest


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    item: ContextItem
    organization_id: str
    project_id: str
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    recency_score: float = 0.0
    authority_score: float = 0.0
    required_memory_scope: str | None = None
    acl_granted: bool = True

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
    request: ContextRequest,
) -> tuple[ContextItem, ...]:
    allowed_memory = set(request.memory_read_scopes)
    scoped: list[RetrievalCandidate] = []
    for candidate in candidates:
        if candidate.item.instruction_authority.value != "none":
            raise ValueError("CONTEXT_RETRIEVAL_AUTHORITY_ESCALATION")
        if candidate.item.layer in {
            ContextLayer.L0_SYSTEM,
            ContextLayer.L2_AGENT,
        }:
            raise ValueError("CONTEXT_RETRIEVAL_STATIC_LAYER_FORBIDDEN")
        if candidate.organization_id != str(request.organization_id):
            continue
        if candidate.project_id != str(request.project_id):
            continue
        if not candidate.acl_granted:
            continue
        if candidate.required_memory_scope is not None:
            exact = candidate.required_memory_scope
            broad = exact.split(":", 1)[0]
            if exact not in allowed_memory and broad not in allowed_memory:
                continue
        if (
            candidate.item.kind is ContextKind.MEMORY
            and candidate.required_memory_scope is None
        ):
            continue
        scoped.append(candidate)

    scoped.sort(
        key=lambda candidate: (
            candidate.hybrid_score,
            candidate.item.priority,
            candidate.recency_score,
            candidate.item.source.version,
            candidate.item.item_id,
        ),
        reverse=True,
    )

    seen: set[tuple[str, str, str, str]] = set()
    output: list[ContextItem] = []
    for candidate in scoped:
        identity = (
            candidate.item.source.source_type,
            candidate.item.source.source_id,
            candidate.item.source.version,
            candidate.item.source.content_hash,
        )
        if identity in seen:
            continue
        seen.add(identity)
        metadata = dict(candidate.item.metadata)
        metadata["retrieval_hybrid_score"] = round(
            candidate.hybrid_score,
            8,
        )
        output.append(
            replace(
                candidate.item,
                relevance_score=candidate.hybrid_score,
                metadata=metadata,
            )
        )
        if len(output) >= request.retrieval_limit:
            break
    return tuple(output)
