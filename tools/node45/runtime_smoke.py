from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from lumi_asset_intelligence import (
    AccessScope,
    AnalyzerOutput,
    AssetIntelligenceService,
    AssetSearchRequest,
    EmbeddingCapability,
    IndexPromotionDecision,
    InMemoryAssetIndexRepository,
    MetadataField,
    VerifiedReadyAsset,
)

ORG = UUID("11111111-1111-4111-8111-111111111111")
ASSET = UUID("22222222-2222-4222-8222-222222222222")
REGISTRY = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


class Catalog:
    def __init__(self) -> None:
        self.asset = VerifiedReadyAsset(
            asset_id=ASSET,
            organization_id=ORG,
            project_id=None,
            brand_id=None,
            status="ready",
            source="upload",
            mime_type="image/png",
            media_kind="image",
            checksum_sha256="a" * 64,
            byte_size=1024,
            rights_level="owned",
            commercial_use=True,
            training_authorized=False,
            permission_tags=(),
            preview_ref="preview://black-cup",
            technical_metadata={"width": 1200, "height": 1200},
            user_metadata={"name": "black cup"},
            created_at=NOW,
        )

    def get_asset(self, organization_id, asset_id):
        if organization_id == ORG and asset_id == ASSET:
            return self.asset
        return None

    def list_ready_assets(self, organization_id):
        return (self.asset,) if organization_id == ORG else ()


class Registry:
    def resolve_multimodal_embedding(self, organization_id):
        assert organization_id == ORG
        return EmbeddingCapability(
            model_key="fixture/embed",
            revision_key="fixture/embed@1",
            registry_version_id=REGISTRY,
            capability_key="embedding.multimodal",
            support="full",
            confidence="verified",
            embedding_version="1",
            dimensions=4,
            source_ref="registry://fixture",
        )


class Analyzer:
    analyzer_id = "fixture"
    analyzer_version = "1"

    def analyze(self, asset, *, embedding_capability):
        assert embedding_capability.dimensions == 4
        return AnalyzerOutput(
            metadata=(
                MetadataField(
                    key="category",
                    value="coffee",
                    source="AUTO",
                    confidence=1.0,
                    analyzer_id="fixture",
                    analyzer_version="1",
                ),
            ),
            semantic_description="matte black coffee cup product photo",
            visual_tags=("coffee", "product"),
            embedding=(1.0, 0.0, 0.0, 0.0),
            perceptual_hash="0000000000000000",
            evidence_refs=("analysis://fixture",),
        )

    def embed_query(self, query, *, embedding_capability):
        assert query and embedding_capability.dimensions == 4
        return (1.0, 0.0, 0.0, 0.0)


def main() -> None:
    repository = InMemoryAssetIndexRepository()
    service = AssetIntelligenceService(
        repository=repository,
        catalog=Catalog(),
        registry=Registry(),
        analyzer=Analyzer(),
    )
    index = service.create_index(
        organization_id=ORG,
        analyzer_version="node45-v1",
        created_at=NOW,
    )
    ready = service.build_index(
        organization_id=ORG,
        index_id=index.id,
        analyzed_at=NOW,
    )
    comparison = service.compare_index_coverage(
        organization_id=ORG,
        candidate_index_id=index.id,
    )
    active = service.activate_index(
        organization_id=ORG,
        index_id=index.id,
        decision=IndexPromotionDecision(
            comparison=comparison,
            approved=True,
            approved_by="smoke",
            reason="initial index",
        ),
        activated_at=NOW,
    )
    hits = service.search(
        AssetSearchRequest(
            scope=AccessScope(organization_id=ORG),
            query="black coffee cup",
        )
    )
    assert ready.coverage_count == 1
    assert active.state == "ACTIVE"
    assert hits and hits[0].asset_id == ASSET
    print("NODE45_ASSET_INTELLIGENCE_RUNTIME_SMOKE_PASS")
    print(
        f"index_version={active.version} coverage={active.coverage_count} "
        f"top_score={hits[0].final_score:.4f}"
    )


if __name__ == "__main__":
    main()
