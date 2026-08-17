from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from lumi_api.identity_engine import (
    CandidateIdentity,
    IdentityAssetRecord,
    IdentityService,
    IdentitySeverity,
    IdentityStatus,
    IdentityType,
    InMemoryIdentityRepository,
    Node18IdentityAssetPolicy,
    Node45AssetIntelligenceSignalProvider,
    ReferenceView,
    RegionEvidence,
    ThresholdProfile,
    UnavailablePolicy,
)
from lumi_api.identity_engine.node45_adapter import AssetIdentityAnalysis

ORG = UUID("11111111-1111-4111-8111-111111111111")
PROJECT = UUID("22222222-2222-4222-8222-222222222222")
ASSET = UUID("44444444-4444-4444-8444-444444444444")
CANDIDATE = UUID("55555555-5555-4555-8555-555555555555")


class Assets:
    def get_identity_asset(self, organization_id, asset_id):
        assert organization_id == ORG
        return IdentityAssetRecord(
            asset_id=asset_id,
            organization_id=ORG,
            status="ready",
            media_kind="image",
            rights_assertion="USER_OWNED",
        )


class Intelligence:
    def __init__(self) -> None:
        region = RegionEvidence(
            source="NODE45_REGION",
            x=0.1,
            y=0.1,
            width=0.6,
            height=0.6,
            detection_confidence=0.98,
            quality=0.97,
            evidence_refs=("asset-analysis://candidate/region",),
        )
        self.values = {
            ASSET: AssetIdentityAnalysis(
                asset_id=ASSET,
                analyzer_version="asset-intel/1",
                content_hash="a" * 64,
                perceptual_hash="ffff0000ffff0000",
                embedding=(1.0, 0.0, 0.0),
                local_signature=(1.0, 0.0, 0.0),
                color_signature=(0.9, 0.1, 0.0),
                brand_region_signature=(1.0, 0.0),
                evidence_refs=("asset-analysis://reference",),
            ),
            CANDIDATE: AssetIdentityAnalysis(
                asset_id=CANDIDATE,
                analyzer_version="asset-intel/1",
                content_hash="b" * 64,
                perceptual_hash="ffff0000ffff0001",
                embedding=(0.99, 0.01, 0.0),
                local_signature=(0.98, 0.02, 0.0),
                color_signature=(0.88, 0.12, 0.0),
                brand_region_signature=(0.99, 0.01),
                region=region,
                evidence_refs=("asset-analysis://candidate",),
            ),
        }

    def get_identity_analysis(self, organization_id, asset_id):
        assert organization_id == ORG
        return self.values.get(asset_id)


def main() -> None:
    profile = ThresholdProfile(
        profile_key="background-replace",
        version=1,
        scenario="background-replace",
        severity=IdentitySeverity.HARD,
        min_score=88,
        min_confidence=0.65,
        min_signal_count=3,
        unavailable_policy=UnavailablePolicy.BLOCK,
    )
    repository = InMemoryIdentityRepository()
    service = IdentityService(
        repository,
        Node45AssetIntelligenceSignalProvider(Intelligence()),
        asset_policy=Node18IdentityAssetPolicy(Assets()),
    )
    reference = service.create_reference_set(
        organization_id=ORG,
        project_id=PROJECT,
        brand_id=None,
        identity_type=IdentityType.PRODUCT,
        name="smoke-product",
        canonical_asset_ids=(ASSET,),
        reference_views=(ReferenceView(asset_id=ASSET, view_key="front"),),
        threshold_profile=profile,
        notes=None,
        created_at=datetime(2026, 8, 17, 12, 30, tzinfo=UTC),
        created_by="smoke",
    )
    result = service.validate(
        organization_id=ORG,
        identity_id=reference.id,
        candidate=CandidateIdentity(asset_id=CANDIDATE),
    )
    assert result.status is IdentityStatus.PASS
    assert result.identity_score is not None and result.identity_score >= 88
    assert result.reference_version == 1
    assert result.candidate_asset_id == CANDIDATE
    print("NODE44_IDENTITY_RUNTIME_SMOKE_PASS")
    print(
        f"reference_version={reference.version} "
        f"score={result.identity_score:.4f} confidence={result.confidence:.4f}"
    )


if __name__ == "__main__":
    main()
