from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

AssetIndexState = Literal[
    "PENDING",
    "ANALYZING",
    "READY",
    "FAILED",
    "STALE",
    "DELETING",
    "DELETED",
]
IndexBuildState = Literal["BUILDING", "READY", "ACTIVE", "RETIRED", "FAILED"]
MetadataSource = Literal["AUTO", "USER", "SYSTEM"]
Rights = Literal["USER_OWNED", "LICENSED", "UNKNOWN"]
DuplicateTier = Literal["EXACT", "PERCEPTUAL_NEAR_DUPLICATE", "SEMANTIC_SIMILAR"]
SearchMode = Literal["HYBRID", "TEXT", "OCR", "SEMANTIC", "SIMILAR_TO"]
UsageSignalType = Literal["SELECTED", "APPROVED", "REJECTED"]
AnalyzerKind = Literal[
    "TECHNICAL",
    "OCR",
    "VISUAL_DESCRIPTION",
    "OBJECT_REGION",
    "EMBEDDING",
    "PERCEPTUAL_HASH",
]


@dataclass(frozen=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    coordinate_space: Literal["NORMALIZED", "PIXELS"] = "NORMALIZED"


@dataclass(frozen=True)
class MetadataField:
    key: str
    value: object
    source: MetadataSource
    confidence: float | None = None
    analyzer_id: str | None = None
    analyzer_version: str | None = None


@dataclass(frozen=True)
class OcrBlock:
    text: str
    confidence: float
    bbox: BoundingBox
    language: str | None = None
    analyzer_id: str | None = None
    analyzer_version: str | None = None


@dataclass(frozen=True)
class AssetRegion:
    label: str
    confidence: float
    bbox: BoundingBox
    region_id: str
    analyzer_id: str | None = None
    analyzer_version: str | None = None


@dataclass(frozen=True)
class AnalyzerModelSnapshot:
    provider_id: str
    model_id: str
    model_version: str
    capability: str
    preprocessor_version: str
    registry_snapshot_id: str


@dataclass(frozen=True)
class AnalyzerBundleSnapshot:
    analyzer_version: str
    ocr: AnalyzerModelSnapshot | None = None
    visual_description: AnalyzerModelSnapshot | None = None
    object_region: AnalyzerModelSnapshot | None = None
    embedding: AnalyzerModelSnapshot | None = None


@dataclass(frozen=True)
class AccessScope:
    organization_id: str
    project_ids: tuple[str, ...] | None = None
    brand_ids: tuple[str, ...] | None = None
    permission_tags: tuple[str, ...] = ()
    allowed_rights: tuple[Rights, ...] = ("USER_OWNED", "LICENSED", "UNKNOWN")
    commercial_use: bool = False


@dataclass(frozen=True)
class VerifiedReadyAsset:
    asset_id: str
    asset_version: str
    organization_id: str
    project_id: str | None
    brand_id: str | None
    checksum_sha256: str
    mime_type: str
    media_type: str
    size_bytes: int
    rights: Rights
    commercial_use_allowed: bool
    training_authorized: bool
    permission_tags: tuple[str, ...] = ()
    preview_ref: str | None = None
    technical_metadata: dict[str, object] = field(default_factory=dict)
    user_metadata: dict[str, object] = field(default_factory=dict)
    state: Literal["READY"] = "READY"


@dataclass(frozen=True)
class AssetIndexVersion:
    index_id: str
    organization_id: str
    version: str
    analyzer_version: str
    embedding_model_id: str
    embedding_model_version: str
    embedding_preprocessor_version: str
    embedding_dimensions: int
    embedding_space_id: str
    registry_snapshot_id: str
    state: IndexBuildState
    created_at: str
    activated_at: str | None = None


@dataclass(frozen=True)
class AnalyzerOutput:
    metadata: tuple[MetadataField, ...] = ()
    ocr_blocks: tuple[OcrBlock, ...] = ()
    regions: tuple[AssetRegion, ...] = ()
    semantic_description: str | None = None
    visual_tags: tuple[str, ...] = ()
    embedding: tuple[float, ...] | None = None
    perceptual_hash: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class AssetAnalysisRecord:
    analysis_id: str
    organization_id: str
    asset_id: str
    asset_version: str
    project_id: str | None
    brand_id: str | None
    index_id: str
    index_version: str
    state: AssetIndexState
    checksum_sha256: str
    mime_type: str
    media_type: str
    rights: Rights
    commercial_use_allowed: bool
    training_authorized: bool
    permission_tags: tuple[str, ...]
    preview_ref: str | None
    metadata: dict[str, MetadataField]
    ocr_blocks: tuple[OcrBlock, ...]
    regions: tuple[AssetRegion, ...]
    semantic_description: str | None
    visual_tags: tuple[str, ...]
    embedding: tuple[float, ...] | None
    perceptual_hash: str | None
    language: str | None
    analyzer_bundle: AnalyzerBundleSnapshot
    created_at: str
    deleted_at: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class DuplicatePolicy:
    policy_version: str
    perceptual_max_hamming: int
    semantic_similarity_floor: float


@dataclass(frozen=True)
class DuplicateEvidence:
    source_asset_id: str
    candidate_asset_id: str
    tier: DuplicateTier
    score: float
    policy_version: str
    detail: str


@dataclass(frozen=True)
class AssetSearchFilters:
    media_types: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()
    brand_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    rights: tuple[Rights, ...] = ()
    created_after: str | None = None
    created_before: str | None = None
    approved_only: bool = False


@dataclass(frozen=True)
class AssetSearchRequest:
    scope: AccessScope
    query: str
    mode: SearchMode = "HYBRID"
    filters: AssetSearchFilters = field(default_factory=AssetSearchFilters)
    query_embedding: tuple[float, ...] | None = None
    similar_to_asset_id: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class UsageSignal:
    organization_id: str
    asset_id: str
    signal: UsageSignalType
    occurred_at: str
    project_id: str | None = None
    actor_id: str | None = None
    training_authorization_granted: bool = False


@dataclass(frozen=True)
class AssetSearchHit:
    asset_id: str
    asset_version: str
    project_id: str | None
    preview_ref: str | None
    rights: Rights
    commercial_use_allowed: bool
    semantic_score: float
    lexical_score: float
    ocr_score: float
    usage_score: float
    final_score: float
    why_matched: tuple[str, ...]
    visual_tags: tuple[str, ...]
    source_ref: str


@dataclass(frozen=True)
class AssetResolverCandidate:
    asset_id: str
    asset_version: str
    preview_ref: str | None
    why_matched: tuple[str, ...]
    rights: Rights
    commercial_use_allowed: bool
    approval_state: Literal["APPROVED", "REJECTED", "SELECTED", "UNKNOWN"]
    similarity: float
    source_ref: str


class AssetAnalyzer(Protocol):
    analyzer_id: str
    analyzer_version: str
    kind: AnalyzerKind

    def analyze(self, asset: VerifiedReadyAsset) -> AnalyzerOutput: ...


class CapabilityRegistryPort(Protocol):
    def resolve_analyzer_bundle(
        self,
        organization_id: str,
        analyzer_version: str,
    ) -> AnalyzerBundleSnapshot: ...


class AssetIndexRepository(Protocol):
    def upsert_analysis(self, record: AssetAnalysisRecord) -> None: ...

    def get_analysis(
        self,
        organization_id: str,
        asset_id: str,
        index_id: str,
    ) -> AssetAnalysisRecord | None: ...

    def scoped_candidates(
        self,
        scope: AccessScope,
        filters: AssetSearchFilters,
        index_id: str,
    ) -> tuple[AssetAnalysisRecord, ...]: ...

    def add_usage_signal(self, signal: UsageSignal) -> None: ...

    def usage_signals(
        self,
        organization_id: str,
        asset_id: str,
    ) -> tuple[UsageSignal, ...]: ...

    def mark_deleted(self, organization_id: str, asset_id: str, deleted_at: str) -> None: ...

    def reconcile_deleted(self, organization_id: str, asset_id: str) -> int: ...
