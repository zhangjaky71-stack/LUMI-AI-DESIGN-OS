from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

IndexState = Literal["BUILDING", "READY", "ACTIVE", "RETIRED", "FAILED"]
AnalysisState = Literal["READY", "STALE", "DELETING", "DELETED", "FAILED"]
MetadataSource = Literal["SYSTEM", "USER", "AUTO"]
RightsLevel = Literal["unknown", "owned", "licensed", "public_domain", "restricted"]
DuplicateTier = Literal["EXACT", "PERCEPTUAL_NEAR_DUPLICATE", "SEMANTIC_SIMILAR"]
SearchMode = Literal["HYBRID", "TEXT", "OCR", "SEMANTIC", "SIMILAR_TO"]
UsageSignalType = Literal["SELECTED", "APPROVED", "REJECTED"]
CapabilitySupport = Literal["full", "partial", "none", "unknown"]


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    coordinate_space: Literal["NORMALIZED", "PIXELS"] = "NORMALIZED"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.x < 0 or self.y < 0:
            raise ValueError("ASSET_INTELLIGENCE_BBOX_INVALID")
        if self.coordinate_space == "NORMALIZED":
            if max(self.x, self.y, self.width, self.height) > 1:
                raise ValueError("ASSET_INTELLIGENCE_BBOX_NORMALIZED_RANGE")
            if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
                raise ValueError("ASSET_INTELLIGENCE_BBOX_OUT_OF_BOUNDS")


@dataclass(frozen=True, slots=True)
class MetadataField:
    key: str
    value: object
    source: MetadataSource
    confidence: float | None = None
    analyzer_id: str | None = None
    analyzer_version: str | None = None

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("ASSET_METADATA_KEY_REQUIRED")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("ASSET_METADATA_CONFIDENCE_INVALID")
        if self.source == "AUTO":
            if self.confidence is None or not self.analyzer_id or not self.analyzer_version:
                raise ValueError("AUTO_METADATA_PROVENANCE_REQUIRED")


@dataclass(frozen=True, slots=True)
class OcrSpan:
    text: str
    confidence: float
    bbox: BoundingBox
    analyzer_id: str
    analyzer_version: str
    language: str | None = None


@dataclass(frozen=True, slots=True)
class AssetRegion:
    region_id: str
    label: str
    confidence: float
    bbox: BoundingBox
    analyzer_id: str
    analyzer_version: str


@dataclass(frozen=True, slots=True)
class EmbeddingCapability:
    model_key: str
    revision_key: str
    registry_version_id: UUID
    capability_key: str
    support: CapabilitySupport
    confidence: str
    embedding_version: str
    dimensions: int
    source_ref: str

    def __post_init__(self) -> None:
        if self.support not in {"full", "partial"}:
            raise ValueError("ASSET_EMBEDDING_CAPABILITY_NOT_SUPPORTED")
        if self.dimensions <= 0 or not self.embedding_version:
            raise ValueError("ASSET_EMBEDDING_CAPABILITY_INCOMPLETE")


@dataclass(frozen=True, slots=True)
class AccessScope:
    organization_id: UUID
    project_ids: tuple[UUID, ...] | None = None
    brand_ids: tuple[UUID, ...] | None = None
    permission_tags: tuple[str, ...] = ()
    allowed_rights: tuple[RightsLevel, ...] = (
        "unknown",
        "owned",
        "licensed",
        "public_domain",
        "restricted",
    )
    commercial_use: bool = False


@dataclass(frozen=True, slots=True)
class VerifiedReadyAsset:
    asset_id: UUID
    organization_id: UUID
    project_id: UUID | None
    brand_id: UUID | None
    status: Literal["ready"]
    source: str
    mime_type: str
    media_kind: str
    checksum_sha256: str
    byte_size: int
    rights_level: RightsLevel
    commercial_use: bool
    training_authorized: bool
    permission_tags: tuple[str, ...]
    preview_ref: str | None
    technical_metadata: dict[str, object]
    user_metadata: dict[str, object]
    created_at: datetime
    deleted_at: datetime | None = None

    @property
    def asset_version(self) -> str:
        return self.checksum_sha256


@dataclass(frozen=True, slots=True)
class AssetIndexVersion:
    id: UUID
    organization_id: UUID
    version: int
    analyzer_version: str
    embedding_model_key: str
    embedding_revision_key: str
    embedding_version: str
    embedding_dimensions: int
    embedding_space_id: str
    registry_version_id: UUID
    state: IndexState
    created_at: datetime
    activated_at: datetime | None = None
    coverage_count: int = 0


@dataclass(frozen=True, slots=True)
class AnalyzerOutput:
    metadata: tuple[MetadataField, ...] = ()
    ocr_spans: tuple[OcrSpan, ...] = ()
    regions: tuple[AssetRegion, ...] = ()
    semantic_description: str | None = None
    visual_tags: tuple[str, ...] = ()
    embedding: tuple[float, ...] | None = None
    perceptual_hash: str | None = None
    language: str | None = None
    local_signature: tuple[float, ...] = ()
    color_signature: tuple[float, ...] = ()
    brand_region_signature: tuple[float, ...] = ()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AssetAnalysisRecord:
    id: UUID
    organization_id: UUID
    asset_id: UUID
    asset_version: str
    project_id: UUID | None
    brand_id: UUID | None
    index_id: UUID
    index_version: int
    state: AnalysisState
    checksum_sha256: str
    source: str
    mime_type: str
    media_kind: str
    rights_level: RightsLevel
    commercial_use: bool
    training_authorized: bool
    permission_tags: tuple[str, ...]
    preview_ref: str | None
    metadata: dict[str, MetadataField]
    ocr_spans: tuple[OcrSpan, ...]
    regions: tuple[AssetRegion, ...]
    semantic_description: str | None
    visual_tags: tuple[str, ...]
    embedding: tuple[float, ...] | None
    perceptual_hash: str | None
    language: str | None
    local_signature: tuple[float, ...]
    color_signature: tuple[float, ...]
    brand_region_signature: tuple[float, ...]
    analyzer_version: str
    embedding_model_key: str
    embedding_revision_key: str
    embedding_version: str
    registry_version_id: UUID
    evidence_refs: tuple[str, ...]
    created_at: datetime
    embedding_id: UUID | None = None
    deleted_at: datetime | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class SearchFilters:
    media_kinds: tuple[str, ...] = ()
    project_ids: tuple[UUID, ...] = ()
    brand_ids: tuple[UUID, ...] = ()
    tags: tuple[str, ...] = ()
    rights: tuple[RightsLevel, ...] = ()
    created_after: datetime | None = None
    created_before: datetime | None = None
    approved_only: bool = False


@dataclass(frozen=True, slots=True)
class AssetSearchRequest:
    scope: AccessScope
    query: str
    mode: SearchMode = "HYBRID"
    filters: SearchFilters = field(default_factory=SearchFilters)
    query_embedding: tuple[float, ...] | None = None
    similar_to_asset_id: UUID | None = None
    limit: int = 20

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("SEARCH_LIMIT_INVALID")
        if self.mode == "SIMILAR_TO" and self.similar_to_asset_id is None:
            raise ValueError("SIMILAR_TO_ASSET_REQUIRED")


@dataclass(frozen=True, slots=True)
class UsageSignal:
    id: UUID
    organization_id: UUID
    asset_id: UUID
    signal: UsageSignalType
    occurred_at: datetime
    project_id: UUID | None = None
    actor_id: str | None = None
    training_authorization_granted: bool = False


@dataclass(frozen=True, slots=True)
class SearchHit:
    asset_id: UUID
    asset_version: str
    project_id: UUID | None
    brand_id: UUID | None
    preview_ref: str | None
    rights_level: RightsLevel
    commercial_use: bool
    semantic_score: float
    lexical_score: float
    ocr_score: float
    usage_score: float
    final_score: float
    why_matched: tuple[str, ...]
    visual_tags: tuple[str, ...]
    source_ref: str


@dataclass(frozen=True, slots=True)
class ResolverCandidate:
    asset_id: UUID
    asset_version: str
    preview_ref: str | None
    why_matched: tuple[str, ...]
    rights_level: RightsLevel
    commercial_use: bool
    approval_state: str
    similarity: float
    source_ref: str
    requires_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class ResolverResult:
    query: str
    index_id: UUID
    index_version: int
    candidates: tuple[ResolverCandidate, ...]


@dataclass(frozen=True, slots=True)
class DuplicatePolicy:
    version: str
    perceptual_max_hamming: int
    semantic_similarity_floor: float


@dataclass(frozen=True, slots=True)
class DuplicateEvidence:
    source_asset_id: UUID
    candidate_asset_id: UUID
    tier: DuplicateTier
    score: float
    policy_version: str
    detail: str
    automatic_delete_allowed: bool = False

    def __post_init__(self) -> None:
        if self.tier == "SEMANTIC_SIMILAR" and self.automatic_delete_allowed:
            raise ValueError("SEMANTIC_SIMILAR_CANNOT_AUTO_DELETE")


@dataclass(frozen=True, slots=True)
class IndexCoverageComparison:
    organization_id: UUID
    active_index_id: UUID | None
    candidate_index_id: UUID
    active_asset_count: int
    candidate_asset_count: int
    common_asset_count: int
    missing_asset_ids: tuple[UUID, ...]
    added_asset_ids: tuple[UUID, ...]
    embedding_space_changed: bool

    @property
    def coverage_ratio(self) -> float:
        if self.active_asset_count == 0:
            return 1.0
        return self.common_asset_count / self.active_asset_count


@dataclass(frozen=True, slots=True)
class IndexPromotionDecision:
    comparison: IndexCoverageComparison
    approved: bool
    approved_by: str
    reason: str


@dataclass(frozen=True, slots=True)
class AnalysisJob:
    id: UUID
    organization_id: UUID
    asset_id: UUID
    index_id: UUID
    idempotency_key: str
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class IndexBuildJob:
    id: UUID
    organization_id: UUID
    index_id: UUID
    idempotency_key: str
    requested_at: datetime


class AssetCatalogPort(Protocol):
    def get_asset(self, organization_id: UUID, asset_id: UUID) -> VerifiedReadyAsset | None: ...

    def list_ready_assets(self, organization_id: UUID) -> tuple[VerifiedReadyAsset, ...]: ...


class AnalyzerPort(Protocol):
    analyzer_id: str
    analyzer_version: str

    def analyze(
        self,
        asset: VerifiedReadyAsset,
        *,
        embedding_capability: EmbeddingCapability,
    ) -> AnalyzerOutput: ...

    def embed_query(
        self,
        query: str,
        *,
        embedding_capability: EmbeddingCapability,
    ) -> tuple[float, ...]: ...


class CapabilityRegistryPort(Protocol):
    def resolve_multimodal_embedding(self, organization_id: UUID) -> EmbeddingCapability: ...


class JobPublisherPort(Protocol):
    def publish(self, job: AnalysisJob | IndexBuildJob) -> None: ...


class AssetIndexRepository(Protocol):
    def reserve_index_version(self, organization_id: UUID) -> int: ...
    def create_index(self, value: AssetIndexVersion) -> None: ...
    def get_index(self, organization_id: UUID, index_id: UUID) -> AssetIndexVersion: ...
    def active_index(self, organization_id: UUID) -> AssetIndexVersion: ...
    def mark_index_ready(
        self, organization_id: UUID, index_id: UUID, coverage_count: int
    ) -> AssetIndexVersion: ...
    def activate_index(
        self,
        organization_id: UUID,
        index_id: UUID,
        activated_at: datetime,
        expected_active_index_id: UUID | None,
    ) -> AssetIndexVersion: ...
    def upsert_analysis(self, value: AssetAnalysisRecord) -> None: ...
    def get_analysis(
        self, organization_id: UUID, asset_id: UUID, index_id: UUID
    ) -> AssetAnalysisRecord | None: ...
    def scoped_candidates(
        self, scope: AccessScope, filters: SearchFilters, index_id: UUID
    ) -> tuple[AssetAnalysisRecord, ...]: ...
    def asset_ids_for_index(self, organization_id: UUID, index_id: UUID) -> set[UUID]: ...
    def add_usage_signal(self, signal: UsageSignal) -> None: ...
    def usage_signals(
        self, organization_id: UUID, asset_id: UUID
    ) -> tuple[UsageSignal, ...]: ...
    def mark_deleted(self, organization_id: UUID, asset_id: UUID, deleted_at: datetime) -> None: ...
    def reconcile_deleted(self, organization_id: UUID, asset_id: UUID) -> int: ...
