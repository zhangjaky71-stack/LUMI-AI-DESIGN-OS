from __future__ import annotations

from dataclasses import replace

from .deletion import AssetIndexDeletionService, DeletionReconciliationResult
from .duplicates import classify_similarity
from .ingestion import AssetIntelligenceIngestor, IngestionResult
from .model import (
    AccessScope,
    AssetIndexRepository,
    AssetIndexVersion,
    AssetResolverCandidate,
    AssetSearchFilters,
    AssetSearchHit,
    AssetSearchRequest,
    DuplicateEvidence,
    DuplicatePolicy,
    UsageSignal,
    VerifiedReadyAsset,
)
from .query_embedding import QueryEmbeddingProvider, attach_query_embedding
from .resolver import AssetResolutionResult, AssetResolver
from .search import AssetSearchEngine


class AssetIntelligenceService:
    def __init__(
        self,
        *,
        repository: AssetIndexRepository,
        ingestor: AssetIntelligenceIngestor,
        search_engine: AssetSearchEngine,
        resolver: AssetResolver,
    ) -> None:
        self._repository = repository
        self._ingestor = ingestor
        self._search_engine = search_engine
        self._resolver = resolver
        self._deletion = AssetIndexDeletionService(repository)

    def ingest(
        self,
        asset: VerifiedReadyAsset,
        index: AssetIndexVersion,
        *,
        analyzed_at: str,
    ) -> IngestionResult:
        return self._ingestor.analyze_ready_asset(asset, index, analyzed_at=analyzed_at)

    def search(
        self,
        request: AssetSearchRequest,
        index: AssetIndexVersion,
        *,
        query_embedder: QueryEmbeddingProvider | None = None,
    ) -> tuple[AssetSearchHit, ...]:
        prepared = request
        if request.mode in {"SEMANTIC", "HYBRID"} and request.query_embedding is None:
            if query_embedder is None:
                raise ValueError("SEMANTIC_QUERY_EMBEDDER_REQUIRED")
            prepared = attach_query_embedding(request, index, query_embedder)
        return self._search_engine.search(prepared, index)

    def resolve_for_agent(
        self,
        request: AssetSearchRequest,
        index: AssetIndexVersion,
        *,
        query_embedder: QueryEmbeddingProvider | None = None,
    ) -> AssetResolutionResult:
        prepared = request
        if request.mode in {"SEMANTIC", "HYBRID"} and request.query_embedding is None:
            if query_embedder is None:
                raise ValueError("SEMANTIC_QUERY_EMBEDDER_REQUIRED")
            prepared = attach_query_embedding(request, index, query_embedder)
        return self._resolver.resolve(prepared, index)

    def find_similar_or_duplicate(
        self,
        *,
        scope: AccessScope,
        source_asset_id: str,
        index: AssetIndexVersion,
        policy: DuplicatePolicy,
        filters: AssetSearchFilters | None = None,
    ) -> tuple[DuplicateEvidence, ...]:
        if scope.organization_id != index.organization_id:
            raise ValueError("DUPLICATE_INDEX_TENANT_MISMATCH")
        safe = self._repository.scoped_candidates(
            scope,
            filters or AssetSearchFilters(),
            index.index_id,
        )
        source = next((item for item in safe if item.asset_id == source_asset_id), None)
        if source is None:
            raise ValueError("DUPLICATE_SOURCE_NOT_ACCESSIBLE")
        evidence: list[DuplicateEvidence] = []
        for candidate in safe:
            evidence.extend(classify_similarity(source, candidate, policy))
        tier_order = {"EXACT": 0, "PERCEPTUAL_NEAR_DUPLICATE": 1, "SEMANTIC_SIMILAR": 2}
        evidence.sort(
            key=lambda item: (
                tier_order[item.tier],
                -item.score,
                item.candidate_asset_id,
            )
        )
        return tuple(evidence)

    def record_usage_signal(self, signal: UsageSignal) -> None:
        # Selection/approval feedback is a ranking feature. Training authorization is a separate
        # explicit field and is never inferred from the signal type.
        self._repository.add_usage_signal(signal)

    def schedule_asset_delete(
        self,
        organization_id: str,
        asset_id: str,
        *,
        deleted_at: str,
    ) -> None:
        self._deletion.schedule_delete(organization_id, asset_id, deleted_at=deleted_at)

    def reconcile_asset_delete(
        self,
        organization_id: str,
        asset_id: str,
    ) -> DeletionReconciliationResult:
        return self._deletion.reconcile(organization_id, asset_id)


def commercial_search_request(request: AssetSearchRequest) -> AssetSearchRequest:
    scope = replace(request.scope, commercial_use=True, allowed_rights=("USER_OWNED", "LICENSED"))
    return replace(request, scope=scope)


def candidate_ids(result: AssetResolutionResult) -> tuple[str, ...]:
    return tuple(candidate.asset_id for candidate in result.candidates)


def rights_risk(candidate: AssetResolverCandidate) -> bool:
    return candidate.rights == "UNKNOWN" or not candidate.commercial_use_allowed
