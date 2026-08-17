from __future__ import annotations

import re
from dataclasses import dataclass

from .duplicates import cosine_similarity
from .model import (
    AssetAnalysisRecord,
    AssetIndexRepository,
    AssetIndexVersion,
    AssetSearchRequest,
    SearchHit,
    UsageSignal,
)

_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class RankingProfile:
    profile_id: str = "asset-rank-v1"
    semantic_weight: float = 0.50
    lexical_weight: float = 0.20
    ocr_weight: float = 0.20
    usage_weight: float = 0.10
    approved_boost: float = 0.35
    selected_boost: float = 0.15
    rejected_penalty: float = 0.50

    def __post_init__(self) -> None:
        weights = (
            self.semantic_weight,
            self.lexical_weight,
            self.ocr_weight,
            self.usage_weight,
        )
        if any(value < 0 for value in weights) or sum(weights) <= 0:
            raise ValueError("ASSET_RANKING_PROFILE_INVALID")


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(value)}


def _token_recall(query: set[str], value: str) -> float:
    if not query:
        return 0.0
    candidate = _tokens(value)
    return len(query & candidate) / len(query)


def _metadata_text(value: AssetAnalysisRecord) -> str:
    items: list[str] = []
    if value.semantic_description:
        items.append(value.semantic_description)
    items.extend(value.visual_tags)
    for field in value.metadata.values():
        if isinstance(field.value, (str, int, float, bool)):
            items.append(str(field.value))
    return " ".join(items)


def _ocr_text(value: AssetAnalysisRecord) -> str:
    return " ".join(span.text for span in value.ocr_spans)


def _usage_score(signals: tuple[UsageSignal, ...], profile: RankingProfile) -> float:
    score = 0.0
    for signal in signals:
        if signal.signal == "APPROVED":
            score += profile.approved_boost
        elif signal.signal == "SELECTED":
            score += profile.selected_boost
        elif signal.signal == "REJECTED":
            score -= profile.rejected_penalty
    return max(-1.0, min(1.0, score))


def approval_state(signals: tuple[UsageSignal, ...]) -> str:
    if not signals:
        return "UNKNOWN"
    return max(signals, key=lambda item: item.occurred_at).signal


class AssetSearchEngine:
    def __init__(
        self,
        repository: AssetIndexRepository,
        profile: RankingProfile | None = None,
    ) -> None:
        self.repository = repository
        self.profile = profile or RankingProfile()

    def search(
        self,
        request: AssetSearchRequest,
        index: AssetIndexVersion,
    ) -> tuple[SearchHit, ...]:
        if index.state != "ACTIVE":
            raise ValueError("SEARCH_REQUIRES_ACTIVE_INDEX")
        if request.scope.organization_id != index.organization_id:
            raise PermissionError("SEARCH_INDEX_TENANT_MISMATCH")
        if request.query_embedding is not None:
            if len(request.query_embedding) != index.embedding_dimensions:
                raise ValueError("QUERY_EMBEDDING_SPACE_MISMATCH")

        # Security invariant: this is the only candidate retrieval call. The repository
        # applies tenant/project/brand/permission/rights filters before any scoring below.
        candidates = self.repository.scoped_candidates(
            request.scope,
            request.filters,
            index.id,
        )

        source: AssetAnalysisRecord | None = None
        if request.mode == "SIMILAR_TO":
            source = next(
                (item for item in candidates if item.asset_id == request.similar_to_asset_id),
                None,
            )
            if source is None:
                raise PermissionError("SIMILAR_TO_SOURCE_NOT_ACCESSIBLE")
            if source.embedding is None:
                raise ValueError("SIMILAR_TO_SOURCE_NOT_EMBEDDED")

        query_tokens = _tokens(request.query)
        hits: list[SearchHit] = []
        for value in candidates:
            if source is not None and value.asset_id == source.asset_id:
                continue
            signals = self.repository.usage_signals(value.organization_id, value.asset_id)
            if request.filters.approved_only and approval_state(signals) != "APPROVED":
                continue

            lexical = _token_recall(query_tokens, _metadata_text(value))
            ocr = _token_recall(query_tokens, _ocr_text(value))
            semantic = 0.0
            query_vector = source.embedding if source is not None else request.query_embedding
            if query_vector is not None and value.embedding is not None:
                semantic = max(0.0, cosine_similarity(query_vector, value.embedding))

            if request.mode == "TEXT" and lexical <= 0:
                continue
            if request.mode == "OCR" and ocr <= 0:
                continue
            if request.mode in {"SEMANTIC", "SIMILAR_TO"} and semantic <= 0:
                continue
            if request.mode == "HYBRID" and max(lexical, ocr, semantic) <= 0:
                continue

            usage = _usage_score(signals, self.profile)
            weighted = (
                semantic * self.profile.semantic_weight
                + lexical * self.profile.lexical_weight
                + ocr * self.profile.ocr_weight
                + usage * self.profile.usage_weight
            )
            if request.mode == "TEXT":
                final = lexical
            elif request.mode == "OCR":
                final = ocr
            elif request.mode in {"SEMANTIC", "SIMILAR_TO"}:
                final = semantic
            else:
                final = weighted

            why: list[str] = []
            if lexical > 0:
                why.append(f"metadata/text token match {lexical:.3f}")
            if ocr > 0:
                why.append(f"OCR token match {ocr:.3f}")
            if semantic > 0:
                why.append(f"semantic similarity {semantic:.3f}")
            if usage > 0:
                why.append("previously selected/approved usage signal")
            elif usage < 0:
                why.append("previous rejection signal lowered ranking")

            hits.append(
                SearchHit(
                    asset_id=value.asset_id,
                    asset_version=value.asset_version,
                    project_id=value.project_id,
                    brand_id=value.brand_id,
                    preview_ref=value.preview_ref,
                    rights_level=value.rights_level,
                    commercial_use=value.commercial_use,
                    semantic_score=semantic,
                    lexical_score=lexical,
                    ocr_score=ocr,
                    usage_score=usage,
                    final_score=final,
                    why_matched=tuple(why),
                    visual_tags=value.visual_tags,
                    source_ref=f"asset:{value.asset_id}@{value.asset_version}",
                )
            )
        hits.sort(key=lambda item: (-item.final_score, str(item.asset_id), item.asset_version))
        return tuple(hits[: request.limit])
