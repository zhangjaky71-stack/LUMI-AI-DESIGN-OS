from .analyzers import (
    AnalyzerContractError,
    FixtureAnalyzer,
    StaticCapabilityRegistry,
    validate_bundle_for_index,
    validate_embedding_dimensions,
)
from .deletion import AssetIndexDeletionService, DeletionReconciliationResult
from .duplicates import classify_similarity, cosine_similarity, perceptual_hamming
from .events import AnalysisJob, AssetReadyEvent, plan_analysis_job
from .identity_adapter import IdentityEvidenceBundle, identity_evidence_from_analysis
from .index_catalog import (
    InMemoryIndexCatalog,
    IndexCoverageComparison,
    IndexPromotionDecision,
    compare_index_coverage,
)
from .ingestion import AssetIntelligenceIngestor, IngestionResult
from .metadata import merge_metadata, system_metadata_from_asset, user_metadata_fields
from .model import *  # noqa: F403
from .query_embedding import QueryEmbeddingProvider, attach_query_embedding
from .repository import InMemoryAssetIndexRepository
from .resolver import AssetResolutionResult, AssetResolver
from .search import AssetRankingProfile, AssetSearchEngine
from .service import AssetIntelligenceService, commercial_search_request

SERVICE_NAME = "asset-intelligence"
VERSION = "1.0.0"

__all__ = [
    "AnalysisJob",
    "AnalyzerContractError",
    "AssetIndexDeletionService",
    "AssetIntelligenceIngestor",
    "AssetIntelligenceService",
    "AssetRankingProfile",
    "AssetReadyEvent",
    "AssetResolutionResult",
    "AssetResolver",
    "AssetSearchEngine",
    "DeletionReconciliationResult",
    "FixtureAnalyzer",
    "IdentityEvidenceBundle",
    "InMemoryAssetIndexRepository",
    "InMemoryIndexCatalog",
    "IndexCoverageComparison",
    "IndexPromotionDecision",
    "IngestionResult",
    "QueryEmbeddingProvider",
    "StaticCapabilityRegistry",
    "attach_query_embedding",
    "classify_similarity",
    "commercial_search_request",
    "compare_index_coverage",
    "cosine_similarity",
    "identity_evidence_from_analysis",
    "merge_metadata",
    "perceptual_hamming",
    "plan_analysis_job",
    "system_metadata_from_asset",
    "user_metadata_fields",
    "validate_bundle_for_index",
    "validate_embedding_dimensions",
]
