from __future__ import annotations

from dataclasses import dataclass

from .model import (
    AssetIndexRepository,
    AssetIndexVersion,
    AssetResolverCandidate,
    AssetSearchRequest,
)
from .search import AssetSearchEngine


@dataclass(frozen=True)
class AssetResolutionResult:
    candidates: tuple[AssetResolverCandidate, ...]
    requires_agent_confirmation: bool = True


class AssetResolver:
    """Agent-facing resolver. It returns explainable candidates and never guesses by filename."""

    def __init__(
        self,
        search_engine: AssetSearchEngine,
        repository: AssetIndexRepository,
    ) -> None:
        self._search_engine = search_engine
        self._repository = repository

    def resolve(
        self,
        request: AssetSearchRequest,
        index: AssetIndexVersion,
    ) -> AssetResolutionResult:
        hits = self._search_engine.search(request, index)
        candidates: list[AssetResolverCandidate] = []
        for hit in hits:
            signals = self._repository.usage_signals(
                request.scope.organization_id,
                hit.asset_id,
            )
            approval_state = "UNKNOWN"
            if signals:
                latest = max(signals, key=lambda item: item.occurred_at)
                approval_state = latest.signal

            why = list(hit.why_matched)
            if hit.rights == "UNKNOWN":
                why.append("rights are UNKNOWN; commercial use requires review")
            elif not hit.commercial_use_allowed:
                why.append("commercial use is not permitted by current asset rights metadata")

            candidates.append(
                AssetResolverCandidate(
                    asset_id=hit.asset_id,
                    asset_version=hit.asset_version,
                    preview_ref=hit.preview_ref,
                    why_matched=tuple(why),
                    rights=hit.rights,
                    commercial_use_allowed=hit.commercial_use_allowed,
                    approval_state=approval_state,
                    similarity=hit.final_score,
                    source_ref=hit.source_ref,
                )
            )
        return AssetResolutionResult(tuple(candidates))
