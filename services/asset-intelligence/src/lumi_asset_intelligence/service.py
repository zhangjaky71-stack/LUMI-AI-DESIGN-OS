from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from .duplicates import classify_similarity
from .ids import new_uuid7
from .metadata import merge_metadata, system_metadata, user_metadata
from .model import (
    AccessScope,
    AnalysisJob,
    AnalyzerPort,
    AssetAnalysisRecord,
    AssetCatalogPort,
    AssetIndexRepository,
    AssetIndexVersion,
    AssetSearchRequest,
    CapabilityRegistryPort,
    DuplicateEvidence,
    DuplicatePolicy,
    IndexBuildJob,
    IndexCoverageComparison,
    IndexPromotionDecision,
    JobPublisherPort,
    ResolverCandidate,
    ResolverResult,
    SearchFilters,
    SearchHit,
    UsageSignal,
)
from .search import AssetSearchEngine, approval_state


class AssetIntelligenceError(ValueError):
    pass


class AssetIntelligenceService:
    def __init__(
        self,
        *,
        repository: AssetIndexRepository,
        catalog: AssetCatalogPort,
        registry: CapabilityRegistryPort,
        analyzer: AnalyzerPort,
        job_publisher: JobPublisherPort | None = None,
    ) -> None:
        self.repository = repository
        self.catalog = catalog
        self.registry = registry
        self.analyzer = analyzer
        self.job_publisher = job_publisher
        self.search_engine = AssetSearchEngine(repository)

    def create_index(
        self,
        *,
        organization_id: UUID,
        analyzer_version: str,
        created_at: datetime,
    ) -> AssetIndexVersion:
        capability = self.registry.resolve_multimodal_embedding(organization_id)
        version = self.repository.reserve_index_version(organization_id)
        value = AssetIndexVersion(
            id=new_uuid7(),
            organization_id=organization_id,
            version=version,
            analyzer_version=analyzer_version,
            embedding_model_key=capability.model_key,
            embedding_revision_key=capability.revision_key,
            embedding_version=capability.embedding_version,
            embedding_dimensions=capability.dimensions,
            embedding_space_id=(
                f"{capability.model_key}:{capability.revision_key}:"
                f"{capability.embedding_version}:{capability.dimensions}"
            ),
            registry_version_id=capability.registry_version_id,
            state="BUILDING",
            created_at=created_at,
        )
        self.repository.create_index(value)
        return value

    def schedule_asset_analysis(
        self,
        *,
        organization_id: UUID,
        asset_id: UUID,
        index_id: UUID,
        requested_at: datetime,
    ) -> AnalysisJob:
        self.repository.get_index(organization_id, index_id)
        asset = self.catalog.get_asset(organization_id, asset_id)
        if asset is None or asset.status != "ready" or asset.deleted_at is not None:
            raise AssetIntelligenceError("ASSET_NOT_READY")
        job = AnalysisJob(
            id=new_uuid7(),
            organization_id=organization_id,
            asset_id=asset_id,
            index_id=index_id,
            idempotency_key=(
                f"asset-intel:{organization_id}:{asset_id}:{asset.asset_version}:{index_id}"
            ),
            requested_at=requested_at,
        )
        if self.job_publisher is not None:
            self.job_publisher.publish(job)
        return job

    def schedule_index_build(
        self,
        *,
        organization_id: UUID,
        index_id: UUID,
        requested_at: datetime,
    ) -> IndexBuildJob:
        index = self.repository.get_index(organization_id, index_id)
        if index.state != "BUILDING":
            raise AssetIntelligenceError("ASSET_INDEX_NOT_BUILDING")
        job = IndexBuildJob(
            id=new_uuid7(),
            organization_id=organization_id,
            index_id=index_id,
            idempotency_key=f"asset-index-build:{organization_id}:{index_id}:v{index.version}",
            requested_at=requested_at,
        )
        if self.job_publisher is not None:
            self.job_publisher.publish(job)
        return job

    def analyze_asset(
        self,
        *,
        organization_id: UUID,
        asset_id: UUID,
        index_id: UUID,
        analyzed_at: datetime,
    ) -> AssetAnalysisRecord:
        index = self.repository.get_index(organization_id, index_id)
        if index.state not in {"BUILDING", "READY", "ACTIVE"}:
            raise AssetIntelligenceError("ASSET_INDEX_NOT_WRITABLE")
        asset = self.catalog.get_asset(organization_id, asset_id)
        if asset is None or asset.organization_id != organization_id:
            raise AssetIntelligenceError("TENANT_RESOURCE_NOT_FOUND")
        if asset.status != "ready" or asset.deleted_at is not None:
            raise AssetIntelligenceError("ASSET_NOT_READY")

        existing = self.repository.get_analysis(organization_id, asset_id, index_id)
        if existing is not None and existing.asset_version == asset.asset_version:
            if existing.state == "READY":
                return existing

        capability = self.registry.resolve_multimodal_embedding(organization_id)
        if capability.model_key != index.embedding_model_key:
            raise AssetIntelligenceError("INDEX_REGISTRY_MODEL_DRIFT")
        if capability.revision_key != index.embedding_revision_key:
            raise AssetIntelligenceError("INDEX_REGISTRY_REVISION_DRIFT")
        if capability.embedding_version != index.embedding_version:
            raise AssetIntelligenceError("INDEX_REGISTRY_EMBEDDING_VERSION_DRIFT")
        if capability.dimensions != index.embedding_dimensions:
            raise AssetIntelligenceError("INDEX_REGISTRY_DIMENSION_DRIFT")

        output = self.analyzer.analyze(asset, embedding_capability=capability)
        if output.embedding is None:
            raise AssetIntelligenceError("ASSET_EMBEDDING_REQUIRED")
        if len(output.embedding) != index.embedding_dimensions:
            raise AssetIntelligenceError("ASSET_EMBEDDING_SPACE_MISMATCH")
        if any(field.source != "AUTO" for field in output.metadata):
            raise AssetIntelligenceError("ANALYZER_METADATA_MUST_BE_AUTO")

        metadata = merge_metadata(
            {},
            system_metadata(
                checksum_sha256=asset.checksum_sha256,
                mime_type=asset.mime_type,
                media_kind=asset.media_kind,
                byte_size=asset.byte_size,
                technical=asset.technical_metadata,
            ),
        )
        metadata = merge_metadata(metadata, user_metadata(asset.user_metadata))
        metadata = merge_metadata(metadata, output.metadata)

        value = AssetAnalysisRecord(
            id=new_uuid7(),
            organization_id=organization_id,
            asset_id=asset.asset_id,
            asset_version=asset.asset_version,
            project_id=asset.project_id,
            brand_id=asset.brand_id,
            index_id=index.id,
            index_version=index.version,
            state="READY",
            checksum_sha256=asset.checksum_sha256,
            source=asset.source,
            mime_type=asset.mime_type,
            media_kind=asset.media_kind,
            rights_level=asset.rights_level,
            commercial_use=asset.commercial_use,
            training_authorized=asset.training_authorized,
            permission_tags=asset.permission_tags,
            preview_ref=asset.preview_ref,
            metadata=metadata,
            ocr_spans=output.ocr_spans,
            regions=output.regions,
            semantic_description=output.semantic_description,
            visual_tags=tuple(sorted(set(output.visual_tags))),
            embedding=output.embedding,
            perceptual_hash=output.perceptual_hash,
            language=output.language,
            local_signature=output.local_signature,
            color_signature=output.color_signature,
            brand_region_signature=output.brand_region_signature,
            analyzer_version=index.analyzer_version,
            embedding_model_key=index.embedding_model_key,
            embedding_revision_key=index.embedding_revision_key,
            embedding_version=index.embedding_version,
            registry_version_id=index.registry_version_id,
            evidence_refs=output.evidence_refs,
            created_at=analyzed_at,
        )
        self.repository.upsert_analysis(value)
        return value

    def build_index(
        self,
        *,
        organization_id: UUID,
        index_id: UUID,
        analyzed_at: datetime,
    ) -> AssetIndexVersion:
        index = self.repository.get_index(organization_id, index_id)
        if index.state != "BUILDING":
            raise AssetIntelligenceError("ASSET_INDEX_NOT_BUILDING")
        for asset in self.catalog.list_ready_assets(organization_id):
            self.analyze_asset(
                organization_id=organization_id,
                asset_id=asset.asset_id,
                index_id=index_id,
                analyzed_at=analyzed_at,
            )
        count = len(self.repository.asset_ids_for_index(organization_id, index_id))
        return self.repository.mark_index_ready(organization_id, index_id, count)

    def compare_index_coverage(
        self,
        *,
        organization_id: UUID,
        candidate_index_id: UUID,
    ) -> IndexCoverageComparison:
        candidate = self.repository.get_index(organization_id, candidate_index_id)
        candidate_ids = self.repository.asset_ids_for_index(organization_id, candidate.id)
        try:
            active = self.repository.active_index(organization_id)
        except LookupError:
            active = None
        active_ids = (
            self.repository.asset_ids_for_index(organization_id, active.id)
            if active is not None
            else set()
        )
        common = active_ids & candidate_ids
        return IndexCoverageComparison(
            organization_id=organization_id,
            active_index_id=active.id if active else None,
            candidate_index_id=candidate.id,
            active_asset_count=len(active_ids),
            candidate_asset_count=len(candidate_ids),
            common_asset_count=len(common),
            missing_asset_ids=tuple(sorted(active_ids - candidate_ids, key=str)),
            added_asset_ids=tuple(sorted(candidate_ids - active_ids, key=str)),
            embedding_space_changed=(
                active is not None and active.embedding_space_id != candidate.embedding_space_id
            ),
        )

    def activate_index(
        self,
        *,
        organization_id: UUID,
        index_id: UUID,
        decision: IndexPromotionDecision,
        activated_at: datetime,
        minimum_coverage_ratio: float = 0.95,
    ) -> AssetIndexVersion:
        if decision.comparison.organization_id != organization_id:
            raise PermissionError("INDEX_PROMOTION_TENANT_MISMATCH")
        if decision.comparison.candidate_index_id != index_id:
            raise AssetIntelligenceError("INDEX_PROMOTION_CANDIDATE_MISMATCH")
        if not decision.approved or not decision.approved_by.strip() or not decision.reason.strip():
            raise AssetIntelligenceError("INDEX_PROMOTION_APPROVAL_REQUIRED")
        if decision.comparison.coverage_ratio < minimum_coverage_ratio:
            raise AssetIntelligenceError("INDEX_PROMOTION_COVERAGE_TOO_LOW")
        return self.repository.activate_index(
            organization_id,
            index_id,
            activated_at,
            decision.comparison.active_index_id,
        )

    def _prepare_search(
        self,
        request: AssetSearchRequest,
        index: AssetIndexVersion,
    ) -> AssetSearchRequest:
        if request.mode in {"HYBRID", "SEMANTIC"} and request.query_embedding is None:
            capability = self.registry.resolve_multimodal_embedding(request.scope.organization_id)
            if (
                capability.model_key != index.embedding_model_key
                or capability.revision_key != index.embedding_revision_key
                or capability.embedding_version != index.embedding_version
                or capability.dimensions != index.embedding_dimensions
            ):
                raise AssetIntelligenceError("ACTIVE_INDEX_REGISTRY_DRIFT")
            vector = self.analyzer.embed_query(
                request.query,
                embedding_capability=capability,
            )
            request = replace(request, query_embedding=vector)
        return request

    def get_active_analysis(
        self,
        *,
        organization_id: UUID,
        asset_id: UUID,
    ) -> AssetAnalysisRecord:
        index = self.repository.active_index(organization_id)
        value = self.repository.get_analysis(organization_id, asset_id, index.id)
        if value is None or value.state != "READY":
            raise AssetIntelligenceError("ASSET_ANALYSIS_NOT_FOUND")
        return value

    def search(self, request: AssetSearchRequest) -> tuple[SearchHit, ...]:
        index = self.repository.active_index(request.scope.organization_id)
        return self.search_engine.search(self._prepare_search(request, index), index)

    def resolve_for_agent(self, request: AssetSearchRequest) -> ResolverResult:
        index = self.repository.active_index(request.scope.organization_id)
        hits = self.search_engine.search(self._prepare_search(request, index), index)
        candidates = tuple(
            ResolverCandidate(
                asset_id=hit.asset_id,
                asset_version=hit.asset_version,
                preview_ref=hit.preview_ref,
                why_matched=hit.why_matched,
                rights_level=hit.rights_level,
                commercial_use=hit.commercial_use,
                approval_state=approval_state(
                    self.repository.usage_signals(request.scope.organization_id, hit.asset_id)
                ),
                similarity=hit.final_score,
                source_ref=hit.source_ref,
                requires_confirmation=True,
            )
            for hit in hits
        )
        return ResolverResult(request.query, index.id, index.version, candidates)

    def find_duplicates(
        self,
        *,
        scope: AccessScope,
        source_asset_id: UUID,
        policy: DuplicatePolicy,
        filters: SearchFilters | None = None,
    ) -> tuple[DuplicateEvidence, ...]:
        index = self.repository.active_index(scope.organization_id)
        safe = self.repository.scoped_candidates(scope, filters or SearchFilters(), index.id)
        source = next((value for value in safe if value.asset_id == source_asset_id), None)
        if source is None:
            raise PermissionError("DUPLICATE_SOURCE_NOT_ACCESSIBLE")
        evidence = [
            item
            for candidate in safe
            for item in classify_similarity(source, candidate, policy)
        ]
        order = {"EXACT": 0, "PERCEPTUAL_NEAR_DUPLICATE": 1, "SEMANTIC_SIMILAR": 2}
        evidence.sort(
            key=lambda item: (
                order[item.tier], -item.score, str(item.candidate_asset_id)
            )
        )
        return tuple(evidence)

    def record_usage_signal(self, signal: UsageSignal) -> None:
        if signal.training_authorization_granted:
            raise AssetIntelligenceError("TRAINING_AUTHORIZATION_REQUIRES_RIGHTS_WORKFLOW")
        self.repository.add_usage_signal(signal)

    def schedule_deleted_asset(
        self,
        *,
        organization_id: UUID,
        asset_id: UUID,
        deleted_at: datetime,
    ) -> None:
        self.repository.mark_deleted(organization_id, asset_id, deleted_at)

    def reconcile_deleted_asset(self, *, organization_id: UUID, asset_id: UUID) -> int:
        return self.repository.reconcile_deleted(organization_id, asset_id)

    @staticmethod
    def commercial_request(request: AssetSearchRequest) -> AssetSearchRequest:
        scope = replace(
            request.scope,
            commercial_use=True,
            allowed_rights=("owned", "licensed", "public_domain"),
        )
        return replace(request, scope=scope)
