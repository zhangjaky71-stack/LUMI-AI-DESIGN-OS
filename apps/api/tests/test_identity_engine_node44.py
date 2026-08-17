from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from lumi_api.identity_engine import (
    CalibrationSample,
    CandidateIdentity,
    IdentityPrivacyDenied,
    IdentityService,
    IdentitySeverity,
    IdentityStatus,
    IdentityType,
    InMemoryIdentityRepository,
    ReferenceView,
    RegionEvidence,
    SampleLabel,
    SignalBundle,
    SignalName,
    SignalScore,
    ThresholdProfile,
    UnavailablePolicy,
    node39_identity_score_adapter,
)

ORG = UUID("11111111-1111-4111-8111-111111111111")
PROJECT = UUID("22222222-2222-4222-8222-222222222222")
BRAND = UUID("33333333-3333-4333-8333-333333333333")
ASSET = UUID("44444444-4444-4444-8444-444444444444")
CANDIDATE = UUID("55555555-5555-4555-8555-555555555555")
NOW = datetime(2026, 8, 17, 11, 30, tzinfo=UTC)


def profile(
    *,
    key: str = "background-replace",
    severity: IdentitySeverity = IdentitySeverity.HARD,
    min_score: float = 88,
    min_confidence: float = 0.65,
    min_signals: int = 2,
) -> ThresholdProfile:
    return ThresholdProfile(
        profile_key=key,
        version=1,
        scenario=key,
        severity=severity,
        min_score=min_score,
        min_confidence=min_confidence,
        min_signal_count=min_signals,
        unavailable_policy=(
            UnavailablePolicy.BLOCK if severity is IdentitySeverity.HARD
            else UnavailablePolicy.REVIEW
        ),
    )


def region(*, quality: float = 1.0, confidence: float = 1.0) -> RegionEvidence:
    return RegionEvidence(
        source="DESIGN_IR_BOUNDS",
        x=0.1,
        y=0.1,
        width=0.5,
        height=0.5,
        detection_confidence=confidence,
        quality=quality,
        evidence_refs=("evidence://region/1",),
    )


def signal(name: SignalName, score: float, confidence: float = 1.0) -> SignalScore:
    return SignalScore(
        name=name,
        score=score,
        confidence=confidence,
        evidence_refs=(f"evidence://signal/{name.value.lower()}",),
    )


class Provider:
    def evaluate(self, reference_set, candidate):
        case = candidate.metadata.get("case")
        values = {
            "logo-exact": (
                signal(SignalName.EXACT_HASH, 100),
                signal(SignalName.PERCEPTUAL, 100),
                signal(SignalName.FEATURE_MATCH, 100),
                signal(SignalName.OCR_WORDMARK, 100),
            ),
            "logo-stretched": (
                signal(SignalName.EXACT_HASH, 0),
                signal(SignalName.PERCEPTUAL, 60),
                signal(SignalName.FEATURE_MATCH, 55),
                signal(SignalName.OCR_WORDMARK, 100),
            ),
            "logo-recolored": (
                signal(SignalName.EXACT_HASH, 0),
                signal(SignalName.PERCEPTUAL, 78),
                signal(SignalName.FEATURE_MATCH, 86),
                signal(SignalName.OCR_WORDMARK, 100),
            ),
            "product-background": (
                signal(SignalName.MULTIMODAL_EMBEDDING, 96),
                signal(SignalName.LOCAL_FEATURE, 95),
                signal(SignalName.SHAPE_COLOR, 92),
                signal(SignalName.BRAND_REGION, 96),
                signal(SignalName.VLM_STRUCTURED, 94),
            ),
            "wrong-sku": (
                signal(SignalName.MULTIMODAL_EMBEDDING, 79),
                signal(SignalName.LOCAL_FEATURE, 65),
                signal(SignalName.SHAPE_COLOR, 75),
                signal(SignalName.BRAND_REGION, 30),
                signal(SignalName.VLM_STRUCTURED, 55),
            ),
            "low-crop": (
                signal(SignalName.MULTIMODAL_EMBEDDING, 98),
                signal(SignalName.LOCAL_FEATURE, 96),
                signal(SignalName.SHAPE_COLOR, 95),
                signal(SignalName.BRAND_REGION, 97),
                signal(SignalName.VLM_STRUCTURED, 95),
            ),
        }[case]
        active_region = None if case == "missing-target" else candidate.declared_region
        return SignalBundle(
            region=active_region,
            signals=values if case != "missing-target" else (),
            provider_version="fixture-provider/1.0",
            evidence_refs=(f"evidence://bundle/{case}",),
        )


def create(service: IdentityService, identity_type: IdentityType, *, p=None, identity_id=None):
    return service.create_reference_set(
        organization_id=ORG,
        project_id=PROJECT,
        brand_id=BRAND if identity_type is not IdentityType.FACE else None,
        identity_type=identity_type,
        name=f"{identity_type.value} identity",
        canonical_asset_ids=(ASSET,),
        reference_views=(ReferenceView(asset_id=ASSET, view_key="front"),),
        threshold_profile=p or profile(),
        notes=None,
        created_at=NOW,
        created_by="user:node44",
        privacy_authorized=identity_type is IdentityType.FACE,
        identity_id=identity_id,
    )


def test_exact_logo_passes_and_stretched_logo_blocks():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    ref = create(service, IdentityType.LOGO, p=profile(min_score=90))
    exact = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            asset_id=CANDIDATE,
            declared_region=region(),
            metadata={"case": "logo-exact"},
        ),
    )
    stretched = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            asset_id=CANDIDATE,
            declared_region=region(),
            metadata={"case": "logo-stretched"},
        ),
    )
    assert exact.status is IdentityStatus.PASS
    assert exact.identity_score == 100
    assert stretched.status is IdentityStatus.BLOCKED
    assert "IDENTITY_SCORE_BELOW_THRESHOLD" in stretched.failure_codes


def test_recolored_logo_is_not_treated_as_exact_identity():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    ref = create(service, IdentityType.LOGO, p=profile(min_score=90))
    result = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            asset_id=CANDIDATE,
            declared_region=region(),
            metadata={"case": "logo-recolored"},
        ),
    )
    assert result.status is IdentityStatus.BLOCKED
    assert result.identity_score < 90


def test_same_product_survives_background_change_but_wrong_sku_blocks():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    ref = create(service, IdentityType.PRODUCT)
    same = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            asset_id=CANDIDATE,
            declared_region=region(),
            metadata={"case": "product-background"},
        ),
    )
    wrong = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            asset_id=CANDIDATE,
            declared_region=region(),
            metadata={"case": "wrong-sku"},
        ),
    )
    assert same.status is IdentityStatus.PASS
    assert same.identity_score > 90
    assert wrong.status is IdentityStatus.BLOCKED
    assert len(wrong.signal_scores) == 5


def test_low_quality_crop_lowers_confidence_and_hard_profile_blocks():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    ref = create(service, IdentityType.PRODUCT)
    result = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            asset_id=CANDIDATE,
            declared_region=region(quality=0.2),
            metadata={"case": "low-crop"},
        ),
    )
    assert result.identity_score > 90
    assert result.confidence < 0.65
    assert result.status is IdentityStatus.BLOCKED
    assert "IDENTITY_CONFIDENCE_LOW" in result.failure_codes


def test_missing_target_and_unavailable_provider_fail_closed_for_hard_identity():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    ref = create(service, IdentityType.PRODUCT)
    missing = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(asset_id=CANDIDATE, metadata={"case": "missing-target"}),
    )
    assert missing.status is IdentityStatus.BLOCKED
    assert missing.identity_score is None
    unavailable = IdentityService(InMemoryIdentityRepository(), None)
    ref2 = create(unavailable, IdentityType.PRODUCT)
    result = unavailable.validate(
        organization_id=ORG,
        identity_id=ref2.id,
        candidate=CandidateIdentity(asset_id=CANDIDATE, declared_region=region()),
    )
    assert result.status is IdentityStatus.BLOCKED
    assert "IDENTITY_SIGNALS_UNAVAILABLE" in result.failure_codes


def test_reference_set_versions_are_immutable_snapshots():
    repo = InMemoryIdentityRepository()
    service = IdentityService(repo, Provider())
    identity_id = UUID("66666666-6666-4666-8666-666666666666")
    v1 = create(service, IdentityType.PRODUCT, identity_id=identity_id)
    v2 = create(service, IdentityType.PRODUCT, identity_id=identity_id, p=profile(min_score=92))
    assert v1.version == 1 and v2.version == 2
    assert v1.snapshot_hash != v2.snapshot_hash
    assert repo.get_latest(ORG, identity_id) == v2


def test_face_requires_explicit_project_scoped_privacy_authorization():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    with pytest.raises(IdentityPrivacyDenied):
        service.create_reference_set(
            organization_id=ORG,
            project_id=None,
            brand_id=None,
            identity_type=IdentityType.FACE,
            name="face",
            canonical_asset_ids=(ASSET,),
            reference_views=(ReferenceView(asset_id=ASSET, view_key="front"),),
            threshold_profile=profile(),
            notes=None,
            created_at=NOW,
            created_by="user:node44",
            privacy_authorized=False,
        )


def test_calibration_selects_data_driven_threshold():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    samples = (
        CalibrationSample(
            sample_id="p1",
            identity_type=IdentityType.LOGO,
            scenario="locked",
            label=SampleLabel.POSITIVE,
            signal_scores=(
                signal(SignalName.EXACT_HASH, 100),
                signal(SignalName.PERCEPTUAL, 98),
            ),
        ),
        CalibrationSample(
            sample_id="p2",
            identity_type=IdentityType.LOGO,
            scenario="locked",
            label=SampleLabel.POSITIVE,
            signal_scores=(
                signal(SignalName.EXACT_HASH, 95),
                signal(SignalName.PERCEPTUAL, 94),
            ),
        ),
        CalibrationSample(
            sample_id="n1",
            identity_type=IdentityType.LOGO,
            scenario="locked",
            label=SampleLabel.NEGATIVE,
            signal_scores=(
                signal(SignalName.EXACT_HASH, 0),
                signal(SignalName.PERCEPTUAL, 50),
            ),
        ),
        CalibrationSample(
            sample_id="m1",
            identity_type=IdentityType.LOGO,
            scenario="locked",
            label=SampleLabel.NEAR_MISS,
            signal_scores=(
                signal(SignalName.EXACT_HASH, 0),
                signal(SignalName.PERCEPTUAL, 82),
            ),
        ),
    )
    report = service.calibrate(
        organization_id=ORG,
        identity_type=IdentityType.LOGO,
        profile_key="locked",
        version=1,
        samples=samples,
        target_precision=0.95,
        created_at=NOW,
    )
    assert report.sample_count == 4
    assert report.metrics.precision >= 0.95
    assert 0 < report.selected_threshold <= 100
    assert len(report.dataset_hash) == 64


def test_node39_adapter_exposes_exact_validation_score_by_node():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    ref = create(service, IdentityType.PRODUCT)
    result = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            node_id="hero-product",
            declared_region=region(),
            metadata={"case": "product-background"},
        ),
    )
    adapter = node39_identity_score_adapter({"hero-product": result})
    assert adapter({"id": "hero-product"}) == pytest.approx(result.identity_score / 100)
    assert adapter({"id": "other"}) is None


def test_node39_identity_preservation_validator_consumes_node44_evidence():
    from lumi_api.constraint_validator.contracts import (
        RuntimeConstraint,
        RuntimeScope,
        ValidationAdapters,
        ValidationPolicy,
    )
    from lumi_api.constraint_validator.validators import validate_identity

    service = IdentityService(InMemoryIdentityRepository(), Provider())
    ref = create(service, IdentityType.PRODUCT)
    result = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            node_id="hero-product",
            declared_region=region(),
            metadata={"case": "wrong-sku"},
        ),
    )
    adapter = node39_identity_score_adapter({"hero-product": result})
    constraint = RuntimeConstraint(
        constraint_id="constraint-identity",
        type="REQUIRE_IDENTITY_SCORE",
        severity="HARD",
        scope=RuntimeScope(node_ids=("hero-product",)),
        parameters={"min_score": 0.88},
    )
    violations = validate_identity(
        {"nodes": {"hero-product": {"id": "hero-product", "kind": "IMAGE"}}},
        constraint,
        {"hero-product"},
        ValidationAdapters(identity_score=adapter),
        ValidationPolicy(),
    )
    assert len(violations) == 1
    assert violations[0].validator == "IdentityPreservationValidator"
    assert violations[0].blocking is True
    assert violations[0].measured_value == pytest.approx(result.identity_score / 100)


def test_low_confidence_node44_evidence_cannot_pass_node39_on_score_alone():
    from lumi_api.constraint_validator.contracts import (
        RuntimeConstraint,
        RuntimeScope,
        ValidationAdapters,
        ValidationPolicy,
    )
    from lumi_api.constraint_validator.validators import validate_identity

    service = IdentityService(InMemoryIdentityRepository(), Provider())
    ref = create(service, IdentityType.PRODUCT)
    result = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(
            node_id="hero-low-crop",
            declared_region=region(quality=0.2),
            metadata={"case": "low-crop"},
        ),
    )
    assert result.identity_score > 0.88 * 100
    adapter = node39_identity_score_adapter({"hero-low-crop": result})
    constraint = RuntimeConstraint(
        constraint_id="constraint-low-confidence",
        type="REQUIRE_IDENTITY_SCORE",
        severity="HARD",
        scope=RuntimeScope(node_ids=("hero-low-crop",)),
        parameters={"min_score": 0.88},
    )
    violations = validate_identity(
        {"nodes": {"hero-low-crop": {"id": "hero-low-crop", "kind": "IMAGE"}}},
        constraint,
        {"hero-low-crop"},
        ValidationAdapters(identity_score=adapter),
        ValidationPolicy(),
    )
    assert len(violations) == 1
    assert violations[0].unavailable is True
    assert violations[0].blocking is True


def test_compare_a_b_type_uses_ephemeral_reference_without_persistence():
    repo = InMemoryIdentityRepository()
    service = IdentityService(repo, Provider())
    result = service.compare(
        organization_id=ORG,
        a=CandidateIdentity(asset_id=ASSET),
        b=CandidateIdentity(
            asset_id=CANDIDATE,
            declared_region=region(),
            metadata={"case": "product-background"},
        ),
        identity_type=IdentityType.PRODUCT,
        profile=profile(),
        created_at=NOW,
    )
    assert result.status is IdentityStatus.PASS
    assert result.identity_type is IdentityType.PRODUCT
    assert repo.validations == []


def test_face_pair_compare_is_not_an_ungoverned_biometric_shortcut():
    service = IdentityService(InMemoryIdentityRepository(), Provider())
    with pytest.raises(IdentityPrivacyDenied):
        service.compare(
            organization_id=ORG,
            a=CandidateIdentity(asset_id=ASSET),
            b=CandidateIdentity(asset_id=CANDIDATE, declared_region=region()),
            identity_type=IdentityType.FACE,
            profile=profile(),
            created_at=NOW,
        )


def test_node45_asset_intelligence_adapter_produces_multi_signal_logo_evidence():
    from lumi_api.identity_engine.node45_adapter import (
        AssetIdentityAnalysis,
        Node45AssetIntelligenceSignalProvider,
    )

    class Source:
        def __init__(self):
            self.values = {
                ASSET: AssetIdentityAnalysis(
                    asset_id=ASSET,
                    analyzer_version="asset-intel/1",
                    content_hash="a" * 64,
                    perceptual_hash="ffff0000ffff0000",
                    local_signature=(1.0, 0.0, 0.0),
                    ocr_text="LUMI COFFEE",
                    evidence_refs=("asset-analysis://reference",),
                ),
                CANDIDATE: AssetIdentityAnalysis(
                    asset_id=CANDIDATE,
                    analyzer_version="asset-intel/1",
                    content_hash="b" * 64,
                    perceptual_hash="ffff0000ffff0000",
                    local_signature=(1.0, 0.0, 0.0),
                    ocr_text="LUMI COFFEE",
                    region=region(),
                    evidence_refs=("asset-analysis://candidate",),
                ),
            }

        def get_identity_analysis(self, organization_id, asset_id):
            assert organization_id == ORG
            return self.values.get(asset_id)

    repo = InMemoryIdentityRepository()
    service = IdentityService(
        repo,
        Node45AssetIntelligenceSignalProvider(Source()),
    )
    ref = create(service, IdentityType.LOGO, p=profile(min_score=90))
    result = service.validate(
        organization_id=ORG,
        identity_id=ref.id,
        candidate=CandidateIdentity(asset_id=CANDIDATE),
    )
    assert result.status is IdentityStatus.PASS
    assert result.identity_score == 100
    assert len(result.signal_scores) == 4
    exact_signal = next(
        item for item in result.signal_scores if item.name is SignalName.EXACT_HASH
    )
    assert exact_signal.available is False
    assert result.provider_version == "node45:asset-intel/1"


def test_node18_reference_asset_policy_enforces_ready_tenant_access():
    from lumi_api.identity_engine.node18_asset_policy import (
        IdentityAssetRecord,
        Node18IdentityAssetPolicy,
    )

    class Source:
        def __init__(self, record):
            self.record = record

        def get_identity_asset(self, organization_id, asset_id):
            del organization_id, asset_id
            return self.record

    ready = IdentityAssetRecord(
        asset_id=ASSET,
        organization_id=ORG,
        status="ready",
        media_kind="image",
        rights_assertion="USER_OWNED",
    )
    service = IdentityService(
        InMemoryIdentityRepository(),
        Provider(),
        asset_policy=Node18IdentityAssetPolicy(Source(ready)),
    )
    ref = create(service, IdentityType.PRODUCT)
    assert ref.canonical_asset_ids == (ASSET,)

    wrong_tenant = IdentityAssetRecord(
        asset_id=ASSET,
        organization_id=UUID("99999999-9999-4999-8999-999999999999"),
        status="ready",
        media_kind="image",
    )
    denied = IdentityService(
        InMemoryIdentityRepository(),
        Provider(),
        asset_policy=Node18IdentityAssetPolicy(Source(wrong_tenant)),
    )
    with pytest.raises(PermissionError, match="TENANT_MISMATCH"):
        create(denied, IdentityType.PRODUCT)
