from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from lumi_asset_intelligence.analyzers import FixtureAnalyzer, StaticCapabilityRegistry
from lumi_asset_intelligence.duplicates import classify_similarity
from lumi_asset_intelligence.events import AssetReadyEvent, plan_analysis_job
from lumi_asset_intelligence.identity_adapter import identity_evidence_from_analysis
from lumi_asset_intelligence.index_catalog import (
    InMemoryIndexCatalog,
    IndexPromotionDecision,
    compare_index_coverage,
)
from lumi_asset_intelligence.ingestion import AssetIntelligenceIngestor
from lumi_asset_intelligence.model import (
    AccessScope,
    AnalyzerBundleSnapshot,
    AnalyzerModelSnapshot,
    AnalyzerOutput,
    AssetIndexVersion,
    AssetSearchFilters,
    AssetSearchRequest,
    BoundingBox,
    DuplicatePolicy,
    MetadataField,
    OcrBlock,
    Rights,
    UsageSignal,
    VerifiedReadyAsset,
)
from lumi_asset_intelligence.query_embedding import attach_query_embedding
from lumi_asset_intelligence.repository import InMemoryAssetIndexRepository
from lumi_asset_intelligence.resolver import AssetResolver
from lumi_asset_intelligence.search import AssetRankingProfile, AssetSearchEngine
from lumi_asset_intelligence.service import AssetIntelligenceService, commercial_search_request

ROOT = Path(__file__).resolve().parents[3]
FIXTURE: dict[str, Any] = json.loads(
    (ROOT / "fixtures/asset-intelligence/node-45-conformance.json").read_text(encoding="utf-8")
)
ORG_A = "00000000-0000-0000-0000-00000000000a"
ORG_B = "00000000-0000-0000-0000-00000000000b"
INDEX_ID = "asset-index:shared-v1"
ANALYZED_AT = "2026-08-14T10:00:00Z"


def _index(org: str, *, index_id: str = INDEX_ID, version: str = "v1") -> AssetIndexVersion:
    return AssetIndexVersion(
        index_id=index_id,
        organization_id=org,
        version=version,
        analyzer_version="analyzer-bundle-v1",
        embedding_model_id="fixture-multimodal",
        embedding_model_version="2026-08-14",
        embedding_dimensions=4,
        embedding_space_id=f"fixture-multimodal@2026-08-14:4d:{version}",
        state="ACTIVE",
        created_at="2026-08-14T09:00:00Z",
        activated_at="2026-08-14T09:05:00Z",
    )


def _bundle(org: str) -> AnalyzerBundleSnapshot:
    embedding = AnalyzerModelSnapshot(
        provider_id="fixture",
        model_id="fixture-multimodal",
        model_version="2026-08-14",
        capability="embedding.multimodal",
        preprocessor_version="fixture-pre-v1",
        registry_snapshot_id=f"registry:{org}:v1",
    )
    return AnalyzerBundleSnapshot(analyzer_version="analyzer-bundle-v1", embedding=embedding)


def _asset(raw: dict[str, Any]) -> VerifiedReadyAsset:
    return VerifiedReadyAsset(
        asset_id=str(raw["asset_id"]),
        asset_version="v1",
        organization_id=str(raw["organization_id"]),
        project_id=str(raw["project_id"]),
        brand_id=None,
        checksum_sha256=str(raw["checksum_sha256"]),
        mime_type="image/png",
        media_type="IMAGE",
        size_bytes=1024,
        rights=cast(Rights, str(raw["rights"])),
        commercial_use_allowed=bool(raw["commercial_use_allowed"]),
        training_authorized=False,
        permission_tags=tuple(str(item) for item in raw.get("permission_tags", [])),
        preview_ref=f"preview:{raw['asset_id']}",
        technical_metadata={"width": 1200, "height": 1200, "color_space": "sRGB"},
        user_metadata={
            "campaign": "manual-approved"
        }
        if str(raw["asset_id"]).endswith("101")
        else {},
    )


def _outputs() -> tuple[FixtureAnalyzer, ...]:
    visual: dict[str, AnalyzerOutput] = {}
    ocr: dict[str, AnalyzerOutput] = {}
    embedding: dict[str, AnalyzerOutput] = {}
    phash: dict[str, AnalyzerOutput] = {}
    for raw in FIXTURE["assets"]:
        asset_id = str(raw["asset_id"])
        visual[asset_id] = AnalyzerOutput(
            metadata=(
                MetadataField("campaign", "auto-derived", "AUTO", 0.7, "fixture", "v1"),
            ),
            semantic_description=str(raw["description"]),
            visual_tags=tuple(str(item) for item in raw["tags"]),
        )
        blocks: list[OcrBlock] = []
        for item in raw["ocr"]:
            bbox = item["bbox"]
            blocks.append(
                OcrBlock(
                    text=str(item["text"]),
                    confidence=float(item["confidence"]),
                    bbox=BoundingBox(
                        x=float(bbox[0]),
                        y=float(bbox[1]),
                        width=float(bbox[2]),
                        height=float(bbox[3]),
                    ),
                    language="en",
                    analyzer_id="fixture-ocr",
                    analyzer_version="analyzer-bundle-v1",
                )
            )
        ocr[asset_id] = AnalyzerOutput(
            ocr_blocks=tuple(blocks),
            language="en" if blocks else None,
        )
        embedding[asset_id] = AnalyzerOutput(
            embedding=tuple(float(value) for value in raw["embedding"])
        )
        phash[asset_id] = AnalyzerOutput(perceptual_hash=str(raw["perceptual_hash"]))
    return (
        FixtureAnalyzer("fixture-embedding", "analyzer-bundle-v1", "EMBEDDING", embedding),
        FixtureAnalyzer("fixture-ocr", "analyzer-bundle-v1", "OCR", ocr),
        FixtureAnalyzer("fixture-phash", "analyzer-bundle-v1", "PERCEPTUAL_HASH", phash),
        FixtureAnalyzer("fixture-visual", "analyzer-bundle-v1", "VISUAL_DESCRIPTION", visual),
    )


def _runtime():
    repository = InMemoryAssetIndexRepository()
    registry = StaticCapabilityRegistry(
        {
            (ORG_A, "analyzer-bundle-v1"): _bundle(ORG_A),
            (ORG_B, "analyzer-bundle-v1"): _bundle(ORG_B),
        }
    )
    ingestor = AssetIntelligenceIngestor(repository, registry, _outputs())
    index_a = _index(ORG_A)
    index_b = _index(ORG_B)
    for raw in FIXTURE["assets"]:
        asset = _asset(raw)
        index = index_a if asset.organization_id == ORG_A else index_b
        result = ingestor.analyze_ready_asset(asset, index, analyzed_at=ANALYZED_AT)
        assert result.error_code is None
        assert result.record is not None

    profile = AssetRankingProfile(
        profile_id="asset-ranking-default",
        version="v1",
        semantic_weight=0.50,
        lexical_weight=0.25,
        ocr_weight=0.20,
        usage_weight=0.05,
        approved_boost=0.8,
        selected_boost=0.4,
        rejected_penalty=1.0,
    )
    search = AssetSearchEngine(repository, profile)
    resolver = AssetResolver(search, repository)
    service = AssetIntelligenceService(
        repository=repository,
        ingestor=ingestor,
        search_engine=search,
        resolver=resolver,
    )
    return repository, ingestor, search, service, index_a, index_b


class FixtureQueryEmbedder:
    provider_id = "fixture"
    model_id = "fixture-multimodal"
    model_version = "2026-08-14"
    preprocessor_version = "fixture-pre-v1"

    def embed_text(self, organization_id: str, text: str) -> tuple[float, ...]:
        assert organization_id == ORG_A
        if "poster" in text.casefold() or "summer" in text.casefold():
            return (0.0, 1.0, 0.0, 0.0)
        return (1.0, 0.0, 0.0, 0.0)


class BadVersionQueryEmbedder(FixtureQueryEmbedder):
    model_version = "2099-01-01"


def _scope(*, permissions: tuple[str, ...] = ()) -> AccessScope:
    return AccessScope(organization_id=ORG_A, permission_tags=permissions)


def test_ingestion_preserves_user_metadata_and_is_idempotent() -> None:
    repository, ingestor, _, _, index, _ = _runtime()
    asset = _asset(FIXTURE["assets"][0])
    first = repository.get_analysis(ORG_A, asset.asset_id, index.index_id)
    assert first is not None
    assert first.metadata["campaign"].source == "USER"
    assert first.metadata["campaign"].value == "manual-approved"
    assert first.metadata["width"].source == "SYSTEM"

    repeated = ingestor.analyze_ready_asset(asset, index, analyzed_at=ANALYZED_AT)
    assert repeated.record == first
    assert "IDEMPOTENT_REUSE" in repeated.warnings


def test_duplicate_tiers_remain_distinct() -> None:
    repository, _, _, _, index, _ = _runtime()
    source = repository.get_analysis(ORG_A, str(FIXTURE["assets"][0]["asset_id"]), index.index_id)
    exact = repository.get_analysis(ORG_A, str(FIXTURE["assets"][1]["asset_id"]), index.index_id)
    near = repository.get_analysis(ORG_A, str(FIXTURE["assets"][2]["asset_id"]), index.index_id)
    semantic = repository.get_analysis(ORG_A, str(FIXTURE["assets"][3]["asset_id"]), index.index_id)
    assert source is not None
    assert exact is not None
    assert near is not None
    assert semantic is not None
    policy = DuplicatePolicy("dup-policy-v1", perceptual_max_hamming=4, semantic_similarity_floor=0.90)

    assert {item.tier for item in classify_similarity(source, exact, policy)} == {
        "EXACT",
        "PERCEPTUAL_NEAR_DUPLICATE",
        "SEMANTIC_SIMILAR",
    }
    assert {item.tier for item in classify_similarity(source, near, policy)} == {
        "PERCEPTUAL_NEAR_DUPLICATE",
        "SEMANTIC_SIMILAR",
    }
    semantic_tiers = {item.tier for item in classify_similarity(source, semantic, policy)}
    assert semantic_tiers == {"SEMANTIC_SIMILAR"}
    assert "EXACT" not in semantic_tiers


def test_ocr_query_returns_poster_and_retains_bbox() -> None:
    repository, _, search, _, index, _ = _runtime()
    request = AssetSearchRequest(scope=_scope(), query="SUMMER 20% OFF", mode="OCR")
    hits = search.search(request, index)
    assert hits[0].asset_id == str(FIXTURE["assets"][4]["asset_id"])
    record = repository.get_analysis(ORG_A, hits[0].asset_id, index.index_id)
    assert record is not None
    assert record.ocr_blocks[0].bbox.width == pytest.approx(0.8)
    assert record.ocr_blocks[0].confidence == pytest.approx(0.98)


def test_semantic_search_cannot_leak_other_tenant_or_private_asset() -> None:
    _, _, _, service, index, _ = _runtime()
    request = AssetSearchRequest(scope=_scope(), query="black coffee cup", mode="SEMANTIC")
    hits = service.search(request, index, query_embedder=FixtureQueryEmbedder())
    ids = {hit.asset_id for hit in hits}
    assert str(FIXTURE["assets"][6]["asset_id"]) not in ids
    assert str(FIXTURE["assets"][7]["asset_id"]) not in ids
    assert str(FIXTURE["assets"][0]["asset_id"]) in ids


def test_permission_scope_can_admit_private_asset_without_cross_tenant_leak() -> None:
    _, _, _, service, index, _ = _runtime()
    request = AssetSearchRequest(
        scope=_scope(permissions=("private-campaign",)),
        query="black coffee cup",
        mode="SEMANTIC",
    )
    hits = service.search(request, index, query_embedder=FixtureQueryEmbedder())
    ids = {hit.asset_id for hit in hits}
    assert str(FIXTURE["assets"][6]["asset_id"]) in ids
    assert str(FIXTURE["assets"][7]["asset_id"]) not in ids


def test_commercial_search_excludes_unknown_rights() -> None:
    _, _, _, service, index, _ = _runtime()
    base = AssetSearchRequest(
        scope=_scope(),
        query="black coffee cup",
        mode="SEMANTIC",
        filters=AssetSearchFilters(media_types=("IMAGE",)),
    )
    request = commercial_search_request(base)
    hits = service.search(request, index, query_embedder=FixtureQueryEmbedder())
    ids = {hit.asset_id for hit in hits}
    assert str(FIXTURE["assets"][5]["asset_id"]) not in ids
    assert all(hit.rights in {"USER_OWNED", "LICENSED"} for hit in hits)
    assert all(hit.commercial_use_allowed for hit in hits)


def test_usage_signal_changes_ranking_without_granting_training_rights() -> None:
    repository, _, _, service, index, _ = _runtime()
    approved_id = str(FIXTURE["assets"][3]["asset_id"])
    signal = UsageSignal(
        organization_id=ORG_A,
        asset_id=approved_id,
        signal="APPROVED",
        occurred_at="2026-08-14T10:30:00Z",
        training_authorization_granted=False,
    )
    service.record_usage_signal(signal)
    stored = repository.usage_signals(ORG_A, approved_id)
    assert stored[-1].training_authorization_granted is False

    request = AssetSearchRequest(scope=_scope(), query="black coffee", mode="HYBRID")
    hits = service.search(request, index, query_embedder=FixtureQueryEmbedder())
    approved_hit = next(hit for hit in hits if hit.asset_id == approved_id)
    assert approved_hit.usage_score > 0


def test_agent_resolver_is_explainable_and_requires_confirmation() -> None:
    _, _, _, service, index, _ = _runtime()
    request = AssetSearchRequest(
        scope=_scope(),
        query="black coffee cup",
        mode="HYBRID",
        limit=3,
    )
    result = service.resolve_for_agent(request, index, query_embedder=FixtureQueryEmbedder())
    assert result.requires_agent_confirmation is True
    assert result.candidates
    assert result.candidates[0].source_ref.startswith("asset:")
    assert result.candidates[0].why_matched


def test_deletion_tombstone_removes_asset_from_retrieval_after_reconciliation() -> None:
    repository, _, search, service, index, _ = _runtime()
    asset_id = str(FIXTURE["assets"][0]["asset_id"])
    service.schedule_asset_delete(ORG_A, asset_id, deleted_at="2026-08-14T11:00:00Z")
    request = AssetSearchRequest(scope=_scope(), query="black cup", mode="TEXT")
    assert asset_id not in {hit.asset_id for hit in search.search(request, index)}
    result = service.reconcile_asset_delete(ORG_A, asset_id)
    assert result.removed_analysis_count == 1
    assert repository.get_analysis(ORG_A, asset_id, index.index_id) is None


def test_reindex_requires_compare_and_audited_switch() -> None:
    catalog = InMemoryIndexCatalog()
    active = _index(ORG_A, index_id="asset-index:v1", version="v1")
    candidate = replace(
        active,
        index_id="asset-index:v2",
        version="v2",
        embedding_model_version="2026-09-01",
        embedding_space_id="fixture-multimodal@2026-09-01:4d",
        state="BUILDING",
        activated_at=None,
    )
    catalog.register(active)
    catalog.register(candidate)
    ready = catalog.mark_ready(ORG_A, candidate.index_id)
    comparison = compare_index_coverage(
        active,
        ready,
        active_asset_ids={"a", "b"},
        candidate_asset_ids={"a", "b", "c"},
    )
    assert comparison.embedding_space_changed is True
    assert comparison.coverage_ratio == 1.0
    promoted = catalog.activate(
        ORG_A,
        candidate.index_id,
        IndexPromotionDecision(comparison, True, "release-manager", "coverage accepted"),
        activated_at="2026-08-14T12:00:00Z",
    )
    assert promoted.state == "ACTIVE"
    assert catalog.get(ORG_A, active.index_id).state == "RETIRED"


def test_query_embedding_model_upgrade_cannot_mix_spaces() -> None:
    _, _, _, _, index, _ = _runtime()
    request = AssetSearchRequest(scope=_scope(), query="coffee", mode="SEMANTIC")
    with pytest.raises(ValueError, match="QUERY_EMBEDDING_MODEL_VERSION_MISMATCH"):
        attach_query_embedding(request, index, BadVersionQueryEmbedder())


def test_identity_adapter_exposes_evidence_not_identity_score() -> None:
    repository, _, _, _, index, _ = _runtime()
    record = repository.get_analysis(
        ORG_A,
        str(FIXTURE["assets"][0]["asset_id"]),
        index.index_id,
    )
    assert record is not None
    evidence = identity_evidence_from_analysis(record)
    assert evidence.asset_version == "v1"
    assert evidence.embedding_model_version == "2026-08-14"
    assert not hasattr(evidence, "identity_score")


def test_analysis_job_is_deterministic_and_async_contract_only() -> None:
    event = AssetReadyEvent("event-1", ORG_A, "asset-1", "v1", "2026-08-14T10:00:00Z")
    first = plan_analysis_job(event, "asset-index:v1")
    second = plan_analysis_job(event, "asset-index:v1")
    assert first == second
    assert first.state == "PENDING"


def test_similar_to_source_must_itself_be_accessible() -> None:
    _, _, search, _, index, _ = _runtime()
    private_id = str(FIXTURE["assets"][6]["asset_id"])
    request = AssetSearchRequest(
        scope=_scope(),
        query="",
        mode="SIMILAR_TO",
        similar_to_asset_id=private_id,
    )
    with pytest.raises(ValueError, match="SIMILAR_TO_SOURCE_NOT_ACCESSIBLE"):
        search.search(request, index)


def test_embedding_dimension_mismatch_fails_indexing() -> None:
    repository = InMemoryAssetIndexRepository()
    asset = _asset(FIXTURE["assets"][0])
    bad_output = {asset.asset_id: AnalyzerOutput(embedding=(1.0, 0.0))}
    analyzer = FixtureAnalyzer("bad", "analyzer-bundle-v1", "EMBEDDING", bad_output)
    ingestor = AssetIntelligenceIngestor(
        repository,
        StaticCapabilityRegistry({(ORG_A, "analyzer-bundle-v1"): _bundle(ORG_A)}),
        (analyzer,),
    )
    result = ingestor.analyze_ready_asset(asset, _index(ORG_A), analyzed_at=ANALYZED_AT)
    assert result.record is None
    assert result.error_code == "EMBEDDING_DIMENSION_MISMATCH"
