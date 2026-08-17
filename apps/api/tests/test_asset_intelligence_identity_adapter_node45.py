from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from lumi_asset_intelligence import (
    AssetAnalysisRecord,
    AssetIndexVersion,
    AssetRegion,
    BoundingBox,
    InMemoryAssetIndexRepository,
    OcrSpan,
)
from lumi_api.asset_intelligence.identity_adapter import IdentityAnalysisSourceAdapter

ORG = UUID("11111111-1111-4111-8111-111111111111")
ASSET = UUID("22222222-2222-4222-8222-222222222222")
INDEX = UUID("33333333-3333-4333-8333-333333333333")
REGISTRY = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def test_node44_adapter_reads_only_active_node45_analysis():
    repo = InMemoryAssetIndexRepository()
    repo.create_index(
        AssetIndexVersion(
            id=INDEX,
            organization_id=ORG,
            version=1,
            analyzer_version="node45-v1",
            embedding_model_key="fixture/embed",
            embedding_revision_key="fixture/embed@1",
            embedding_version="1",
            embedding_dimensions=4,
            embedding_space_id="fixture:1:4",
            registry_version_id=REGISTRY,
            state="ACTIVE",
            created_at=NOW,
            activated_at=NOW,
            coverage_count=1,
        )
    )
    repo._active[ORG] = INDEX
    repo.upsert_analysis(
        AssetAnalysisRecord(
            id=UUID("55555555-5555-4555-8555-555555555555"),
            organization_id=ORG,
            asset_id=ASSET,
            asset_version="a" * 64,
            project_id=None,
            brand_id=None,
            index_id=INDEX,
            index_version=1,
            state="READY",
            checksum_sha256="a" * 64,
            source="upload",
            mime_type="image/png",
            media_kind="image",
            rights_level="owned",
            commercial_use=True,
            training_authorized=False,
            permission_tags=(),
            preview_ref=None,
            metadata={},
            ocr_spans=(
                OcrSpan(
                    text="DREAM CUP",
                    confidence=0.99,
                    bbox=BoundingBox(0.1, 0.1, 0.5, 0.2),
                    analyzer_id="ocr",
                    analyzer_version="1",
                ),
            ),
            regions=(
                AssetRegion(
                    region_id="product:1",
                    label="product",
                    confidence=0.96,
                    bbox=BoundingBox(0.1, 0.1, 0.7, 0.7),
                    analyzer_id="detector",
                    analyzer_version="1",
                ),
            ),
            semantic_description="black product cup",
            visual_tags=("coffee", "product"),
            embedding=(1.0, 0.0, 0.0, 0.0),
            perceptual_hash="0000000000000000",
            language="en",
            local_signature=(1.0, 0.0),
            color_signature=(0.1, 0.2),
            brand_region_signature=(0.8, 0.9),
            analyzer_version="node45-v1",
            embedding_model_key="fixture/embed",
            embedding_revision_key="fixture/embed@1",
            embedding_version="1",
            registry_version_id=REGISTRY,
            evidence_refs=("asset-analysis://fixture",),
            created_at=NOW,
        )
    )
    value = IdentityAnalysisSourceAdapter(repo).get_identity_analysis(ORG, ASSET)
    assert value is not None
    assert value.asset_id == ASSET
    assert value.embedding == (1.0, 0.0, 0.0, 0.0)
    assert value.ocr_text == "DREAM CUP"
    assert value.region is not None
    assert value.region.detection_confidence == 0.96
