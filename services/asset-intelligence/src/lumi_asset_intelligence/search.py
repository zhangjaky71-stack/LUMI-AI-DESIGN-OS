from __future__ import annotations

import re
from dataclasses import dataclass

from .duplicates import cosine_similarity
from .model import (
    AssetAnalysisRecord,
    AssetIndexRepository,
    AssetIndexVersion,
    AssetSearchHit,
    AssetSearchRequest,
    UsageSignal,
)

_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)


@dataclass(frozen=True)
class AssetRankingProfile:
    profile_id: str
    version: str
    semantic_weight: float
    lexical_weight: float
    ocr_weight: float
    usage_weight: float
    approved_boost: float
    selected_boost: float
    rejected_penalty: float

    def validate(self) -> None:
        weights = (
            self.semantic_weight,
            self.lexical_weight,
            self.ocr_weight,
            self.usage_weight,
        )
        if any(weight < 0 for weight in weights):
            raise ValueError("NEGATIVE_RANKING_WEIGHT")
        if sum(weights) <= 0:
            raise ValueError("EMPTY_RANKING_PROFILE")


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(value)}


def _token_recall(query: set[str], value: str) -> float:
    if not query:
        return 0.0
    candidate = _tokens(value)
    return len(query & candidate) / len(query)


def _metadata_text(record: AssetAnalysisRecord) -> str:
    values: list[str] = []
    if record.semantic_description:
        values.append(record.semantic_description)
    values.extend(record.visual_tags)
    for field in record.metadata.values():
        if isinstance(field.value, str):
            values.append(field.value)
        elif isinstance(field.value, (int, float, bool)):
            values.append(str(field.value))
    return " ".join(values)


def _ocr_text(record: AssetAnalysisRecord) -> str:
    return " ".join(block.text for block in record.ocr_blocks)


def _usage_score(signals: tuple[UsageSignal, ...], profile: AssetRankingProfile) -> float:
    score = 0.0
    for signal in signals:
        if signal.signal == "APPROVED":
            score += profile.approved_boost
        elif signal.signal == "SELECTED":
            score += profile.selected_boost
        elif signal.signal == "REJECTED":
            score -= profile.rejected_penalty
    return max(-1.0, min(1.0, score))


def _approval_state(signals: tuple[UsageSignal, ...]) -> str:
    if not signals:
        return "UNKNOWN"
    latest = max(signals, key=lambda item: item.occurred_at)
    return latest.signal


class AssetSearchEngine:
    def __init__(self, repository: AssetIndexRepository, profile: AssetRankingProfile) -> None:
        profile.validate()
        self._repository = repository
        self._profile = profile

    def search(
        self,
        request: AssetSearchRequest,
        index: AssetIndexVersion,
    ) -> tuple[AssetSearchHit, ...]:
        if index.state != "ACTIVE":
            raise ValueError("SEARCH_REQUIRES_ACTIVE_INDEX")
        if request.scope.organization_id != index.organization_id:
            raise ValueError("SEARCH_INDEX_TENANT_MISMATCH")
        if request.limit <= 0:
            raise ValueError("SEARCH_LIMIT_MUST_BE_POSITIVE")
        if request.query_embedding is not None:
            if len(request.query_embedding) != index.embedding_dimensions:
                raise ValueError("QUERY_EMBEDDING_SPACE_MISMATCH")

        # Critical security invariant: this is the only candidate retrieval call. The repository
        # applies organization/project/brand/permission/rights filters before any scoring below.
        candidates = self._repository.scoped_candidates(request.scope, request.filters, index.index_id)

        source: AssetAnalysisRecord | None = None
        if request.mode == "SIMILAR_TO":
            if not request.similar_to_asset_id:
                raise ValueError("SIMILAR_TO_ASSET_REQUIRED")
            source = next(
                (item for item in candidates if item.asset_id == request.similar_to_asset_id),
                None,
            )
            if source is None:
                raise ValueError("SIMILAR_TO_SOURCE_NOT_ACCESSIBLE")
            if source.embedding is None:
                raise ValueError("SIMILAR_TO_SOURCE_NOT_EMBEDDED")

        query_tokens = _tokens(request.query)
        hits: list[AssetSearchHit] = []
        for record in candidates:
            if source is not None and record.asset_id == source.asset_id:
                continue

            signals = self._repository.usage_signals(record.organization_id, record.asset_id)
            if request.filters.approved_only and _approval_state(signals) != "APPROVED":
                continue

            lexical = _token_recall(query_tokens, _metadata_text(record))
            ocr = _token_recall(query_tokens, _ocr_text(record))
            semantic = 0.0
            semantic_vector = request.query_embedding
            if source is not None:
                semantic_vector = source.embedding
            if semantic_vector is not None and record.embedding is not None:
                semantic = max(0.0, cosine_similarity(semantic_vector, record.embedding))

            usage = _usage_score(signals, self._profile)
            weighted = (
                semantic * self._profile.semantic_weight
                + lexical * self._profile.lexical_weight
                + ocr * self._profile.ocr_weight
                + usage * self._profile.usage_weight
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
            if not why:
                continue

            hits.append(
                AssetSearchHit(
                    asset_id=record.asset_id,
                    asset_version=record.asset_version,
                    project_id=record.project_id,
                    preview_ref=record.preview_ref,
                    rights=record.rights,
                    commercial_use_allowed=record.commercial_use_allowed,
                    semantic_score=semantic,
                    lexical_score=lexical,
                    ocr_score=ocr,
                    usage_score=usage,
                    final_score=final,
                    why_matched=tuple(why),
                    visual_tags=record.visual_tags,
                    source_ref=f"asset:{record.asset_id}@{record.asset_version}",
                )
            )

        hits.sort(key=lambda hit: (-hit.final_score, hit.asset_id, hit.asset_version))
        return tuple(hits[: request.limit])
