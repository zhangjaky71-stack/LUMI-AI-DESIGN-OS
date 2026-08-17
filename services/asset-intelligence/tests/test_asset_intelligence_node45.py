from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from uuid import UUID

import pytest

from lumi_asset_intelligence import (
    AccessScope, AnalyzerOutput, AssetIntelligenceError, AssetIntelligenceService,
    AssetSearchRequest, BoundingBox, DuplicatePolicy, EmbeddingCapability,
    InMemoryAssetIndexRepository, IndexPromotionDecision, MetadataField, OcrSpan,
    SearchFilters, UsageSignal, VerifiedReadyAsset, new_uuid7,
)

ORG = UUID("11111111-1111-4111-8111-111111111111")
PROJECT = UUID("22222222-2222-4222-8222-222222222222")
REGISTRY = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


class Registry:
    version = "emb-v1"
    dimensions = 4

    def resolve_multimodal_embedding(self, organization_id):
        assert organization_id == ORG
        return EmbeddingCapability(
            "provider/mm", "provider/mm@1", REGISTRY, "embedding.multimodal",
            "full", "verified", self.version, self.dimensions, "registry://node23/v1",
        )


class Catalog:
    def __init__(self, assets):
        self.assets = {a.asset_id: a for a in assets}

    def get_asset(self, organization_id, asset_id):
        value = self.assets.get(asset_id)
        return value if value and value.organization_id == organization_id else None

    def list_ready_assets(self, organization_id):
        return tuple(
            a for a in self.assets.values()
            if a.organization_id == organization_id and a.deleted_at is None
        )


class Analyzer:
    analyzer_id = "fixture"
    analyzer_version = "1"

    def analyze(self, asset, *, embedding_capability):
        name = asset.user_metadata["name"]
        vectors = {
            "black": (1.0, 0.0, 0.0, 0.0),
            "black-copy": (0.99, 0.01, 0.0, 0.0),
            "red": (0.0, 1.0, 0.0, 0.0),
            "menu": (0.0, 0.0, 1.0, 0.0),
            "private": (0.0, 0.0, 0.0, 1.0),
        }
        vector = vectors[name]
        if embedding_capability.dimensions != 4:
            vector = tuple(float(i == 0) for i in range(embedding_capability.dimensions))
        ocr = ()
        if name == "menu":
            ocr = (
                OcrSpan(
                    "SUMMER LATTE 39", 0.98, BoundingBox(0.1, 0.1, 0.6, 0.2),
                    "fixture", "1", "en",
                ),
            )
        return AnalyzerOutput(
            metadata=(
                MetadataField(
                    "name", "AUTO", "AUTO", 0.9, "fixture", "1"
                ),
            ),
            ocr_spans=ocr,
            semantic_description=f"studio {name} coffee product",
            visual_tags=("coffee", "product") if "black" in name else ("document",),
            embedding=vector,
            perceptual_hash={
                "black": "0000000000000000",
                "black-copy": "0000000000000001",
                "red": "ffffffffffffffff",
            }.get(name, "1234567890abcdef"),
            local_signature=vector,
            color_signature=vector,
            brand_region_signature=vector,
            evidence_refs=(f"analysis://{asset.asset_id}",),
        )

    def embed_query(self, query, *, embedding_capability):
        if "black" in query or "coffee" in query:
            value = (1.0, 0.0, 0.0, 0.0)
        elif "red" in query:
            value = (0.0, 1.0, 0.0, 0.0)
        else:
            value = (0.0, 0.0, 1.0, 0.0)
        return value[: embedding_capability.dimensions]


class Publisher:
    def __init__(self):
        self.jobs = []

    def publish(self, job):
        self.jobs.append(job)


def make_asset(
    name, *, rights="owned", commercial=True, permission_tags=(), checksum=None
):
    digest = checksum or {
        "black": "a" * 64, "black-copy": "b" * 64,
        "red": "c" * 64, "menu": "d" * 64, "private": "e" * 64,
    }[name]
    return VerifiedReadyAsset(
        new_uuid7(), ORG, PROJECT, None, "ready", "upload", "image/png", "image",
        digest, 1000, rights, commercial, False, permission_tags,
        f"preview://{name}", {"width": 1000}, {"name": name}, NOW,
    )


def setup(*assets, registry=None, publisher=None):
    repo = InMemoryAssetIndexRepository()
    service = AssetIntelligenceService(
        repository=repo, catalog=Catalog(assets), registry=registry or Registry(),
        analyzer=Analyzer(), job_publisher=publisher,
    )
    return service, repo


def activate(service):
    index = service.create_index(
        organization_id=ORG, analyzer_version="an-v1", created_at=NOW
    )
    service.build_index(organization_id=ORG, index_id=index.id, analyzed_at=NOW)
    comparison = service.compare_index_coverage(
        organization_id=ORG, candidate_index_id=index.id
    )
    return service.activate_index(
        organization_id=ORG, index_id=index.id,
        decision=IndexPromotionDecision(comparison, True, "user", "approved"),
        activated_at=NOW,
    )


def test_search_metadata_ocr_duplicates_permissions_rights_and_feedback():
    black = make_asset("black")
    copy = make_asset("black-copy", checksum="a" * 64)
    red = make_asset("red")
    menu = make_asset("menu", rights="unknown", commercial=False)
    private = make_asset("private", permission_tags=("secret",))
    service, _ = setup(black, copy, red, menu, private)
    active = activate(service)
    value = service.get_active_analysis(organization_id=ORG, asset_id=black.asset_id)
    assert value.metadata["name"].source == "USER"
    assert value.embedding and value.perceptual_hash and value.evidence_refs
    hits = service.search(AssetSearchRequest(AccessScope(ORG), "black coffee"))
    assert hits[0].asset_id == black.asset_id and hits[0].why_matched
    resolved = service.resolve_for_agent(AssetSearchRequest(AccessScope(ORG), "black"))
    assert resolved.index_id == active.id and resolved.candidates[0].requires_confirmation
    ocr = service.search(AssetSearchRequest(AccessScope(ORG), "LATTE 39", mode="OCR"))
    assert ocr[0].asset_id == menu.asset_id
    hidden = service.search(AssetSearchRequest(AccessScope(ORG), "private", mode="TEXT"))
    assert not hidden
    visible = service.search(
        AssetSearchRequest(
            AccessScope(ORG, permission_tags=("secret",)), "private", mode="TEXT"
        )
    )
    assert visible[0].asset_id == private.asset_id
    commercial = service.commercial_request(
        AssetSearchRequest(AccessScope(ORG), "menu", mode="TEXT")
    )
    assert not service.search(commercial)
    duplicates = service.find_duplicates(
        scope=AccessScope(ORG), source_asset_id=black.asset_id,
        policy=DuplicatePolicy("v1", 2, 0.95),
    )
    assert [d.tier for d in duplicates[:3]] == [
        "EXACT", "PERCEPTUAL_NEAR_DUPLICATE", "SEMANTIC_SIMILAR"
    ]
    service.record_usage_signal(
        UsageSignal(new_uuid7(), ORG, copy.asset_id, "APPROVED", NOW)
    )
    approved = service.search(
        AssetSearchRequest(
            AccessScope(ORG), "black-copy", mode="TEXT",
            filters=SearchFilters(approved_only=True),
        )
    )
    assert [hit.asset_id for hit in approved] == [copy.asset_id]


def test_similar_to_source_must_be_accessible():
    private = make_asset("private", permission_tags=("secret",))
    public = make_asset("black")
    service, _ = setup(private, public)
    activate(service)
    with pytest.raises(PermissionError, match="SOURCE_NOT_ACCESSIBLE"):
        service.search(
            AssetSearchRequest(
                AccessScope(ORG), "", mode="SIMILAR_TO",
                similar_to_asset_id=private.asset_id,
            )
        )


def test_async_jobs_do_not_run_analyzer_inline_and_training_grant_is_forbidden():
    black = make_asset("black")
    publisher = Publisher()
    service, repo = setup(black, publisher=publisher)
    index = service.create_index(
        organization_id=ORG, analyzer_version="an-v1", created_at=NOW
    )
    analysis_job = service.schedule_asset_analysis(
        organization_id=ORG, asset_id=black.asset_id,
        index_id=index.id, requested_at=NOW,
    )
    build_job = service.schedule_index_build(
        organization_id=ORG, index_id=index.id, requested_at=NOW
    )
    assert publisher.jobs == [analysis_job, build_job]
    assert repo.get_analysis(ORG, black.asset_id, index.id) is None
    with pytest.raises(AssetIntelligenceError, match="RIGHTS_WORKFLOW"):
        service.record_usage_signal(
            UsageSignal(
                new_uuid7(), ORG, black.asset_id, "APPROVED", NOW,
                training_authorization_granted=True,
            )
        )


def test_reindex_switch_delete_and_registry_drift():
    black = make_asset("black")
    registry = Registry()
    service, repo = setup(black, registry=registry)
    first = activate(service)
    registry.version = "emb-v2"
    second = service.create_index(
        organization_id=ORG, analyzer_version="an-v2", created_at=NOW
    )
    service.build_index(organization_id=ORG, index_id=second.id, analyzed_at=NOW)
    comparison = service.compare_index_coverage(
        organization_id=ORG, candidate_index_id=second.id
    )
    promoted = service.activate_index(
        organization_id=ORG, index_id=second.id,
        decision=IndexPromotionDecision(comparison, True, "u", "reindex"),
        activated_at=NOW + timedelta(seconds=1),
    )
    assert promoted.version == 2 and repo.get_index(ORG, first.id).state == "RETIRED"
    service.schedule_deleted_asset(
        organization_id=ORG, asset_id=black.asset_id, deleted_at=NOW
    )
    assert not service.search(AssetSearchRequest(AccessScope(ORG), "black", mode="TEXT"))
    assert service.reconcile_deleted_asset(
        organization_id=ORG, asset_id=black.asset_id
    ) == 2
    third = service.create_index(
        organization_id=ORG, analyzer_version="an-v3", created_at=NOW
    )
    registry.dimensions = 8
    with pytest.raises(AssetIntelligenceError, match="DIMENSION_DRIFT"):
        service.analyze_asset(
            organization_id=ORG, asset_id=black.asset_id,
            index_id=third.id, analyzed_at=NOW,
        )


def test_promotion_rejects_low_coverage_and_stale_active_head():
    black = make_asset("black")
    service, repo = setup(black)
    activate(service)
    low = service.create_index(
        organization_id=ORG, analyzer_version="low", created_at=NOW
    )
    repo.mark_index_ready(ORG, low.id, 0)
    low_compare = service.compare_index_coverage(
        organization_id=ORG, candidate_index_id=low.id
    )
    with pytest.raises(AssetIntelligenceError, match="COVERAGE_TOO_LOW"):
        service.activate_index(
            organization_id=ORG, index_id=low.id,
            decision=IndexPromotionDecision(low_compare, True, "u", "low"),
            activated_at=NOW,
        )
    one = service.create_index(organization_id=ORG, analyzer_version="one", created_at=NOW)
    two = service.create_index(organization_id=ORG, analyzer_version="two", created_at=NOW)
    service.build_index(organization_id=ORG, index_id=one.id, analyzed_at=NOW)
    service.build_index(organization_id=ORG, index_id=two.id, analyzed_at=NOW)
    c1 = service.compare_index_coverage(organization_id=ORG, candidate_index_id=one.id)
    c2 = service.compare_index_coverage(organization_id=ORG, candidate_index_id=two.id)
    service.activate_index(
        organization_id=ORG, index_id=one.id,
        decision=IndexPromotionDecision(c1, True, "u", "one"), activated_at=NOW,
    )
    with pytest.raises(ValueError, match="ACTIVE_HEAD_CONFLICT"):
        service.activate_index(
            organization_id=ORG, index_id=two.id,
            decision=IndexPromotionDecision(c2, True, "u", "two"), activated_at=NOW,
        )


def test_index_versions_are_unique_under_thread_contention():
    repo = InMemoryAssetIndexRepository()
    barrier = Barrier(8)
    values = []

    def worker():
        barrier.wait()
        values.append(repo.reserve_index_version(ORG))

    threads = [Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(values) == list(range(1, 9))
