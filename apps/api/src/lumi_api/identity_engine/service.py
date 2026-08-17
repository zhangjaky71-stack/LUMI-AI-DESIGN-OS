from __future__ import annotations

from datetime import datetime
from uuid import UUID

from lumi_api.domain.ids import new_uuid7

from .calibration import calibrate_threshold
from .contracts import (
    CalibrationReport,
    CalibrationSample,
    CandidateIdentity,
    IdentityReferenceSet,
    IdentitySeverity,
    IdentityStatus,
    IdentityType,
    IdentityValidationResult,
    ReferenceView,
    SignalBundle,
    ThresholdProfile,
    UnavailablePolicy,
    canonical_hash,
)
from .ports import IdentityAssetPolicy, IdentityRepository, IdentitySignalProvider
from .scoring import combine_signals


class IdentityValidationUnavailable(RuntimeError):
    code = "IDENTITY_VALIDATION_UNAVAILABLE"


class IdentityPrivacyDenied(PermissionError):
    code = "IDENTITY_PRIVACY_POLICY_DENIED"


class IdentityService:
    def __init__(
        self,
        repository: IdentityRepository,
        signal_provider: IdentitySignalProvider | None,
        asset_policy: IdentityAssetPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.signal_provider = signal_provider
        self.asset_policy = asset_policy

    def create_reference_set(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        brand_id: UUID | None,
        identity_type: IdentityType,
        name: str,
        canonical_asset_ids: tuple[UUID, ...],
        reference_views: tuple[ReferenceView, ...],
        threshold_profile: ThresholdProfile,
        notes: str | None,
        created_at: datetime,
        created_by: str,
        privacy_authorized: bool = False,
        identity_id: UUID | None = None,
    ) -> IdentityReferenceSet:
        if identity_type is IdentityType.FACE and (
            not privacy_authorized or project_id is None or brand_id is not None
        ):
            raise IdentityPrivacyDenied(
                "FACE identity requires explicit project-scoped authorization"
            )
        if self.asset_policy is not None:
            self.asset_policy.assert_reference_assets_allowed(
                organization_id,
                canonical_asset_ids,
                identity_type=identity_type.value,
            )
        identity_id = identity_id or new_uuid7()
        version = self.repository.reserve_version(organization_id, identity_id)
        snapshot_payload = {
            "identity_id": str(identity_id),
            "organization_id": str(organization_id),
            "project_id": str(project_id) if project_id else None,
            "brand_id": str(brand_id) if brand_id else None,
            "identity_type": identity_type.value,
            "canonical_asset_ids": [str(v) for v in canonical_asset_ids],
            "reference_views": [v.model_dump(mode="json") for v in reference_views],
            "threshold_profile": threshold_profile.model_dump(mode="json"),
            "notes": notes,
            "version": version,
        }
        value = IdentityReferenceSet(
            id=identity_id,
            organization_id=organization_id,
            project_id=project_id,
            brand_id=brand_id,
            identity_type=identity_type,
            name=name,
            canonical_asset_ids=canonical_asset_ids,
            reference_views=reference_views,
            notes=notes,
            threshold_profile=threshold_profile,
            version=version,
            snapshot_hash=canonical_hash(snapshot_payload),
            created_at=created_at,
            created_by=created_by,
            privacy_authorized=privacy_authorized,
        )
        self.repository.save_reference_set(value)
        return value

    def create_version(
        self,
        *,
        organization_id: UUID,
        identity_id: UUID,
        canonical_asset_ids: tuple[UUID, ...],
        reference_views: tuple[ReferenceView, ...],
        threshold_profile: ThresholdProfile,
        notes: str | None,
        created_at: datetime,
        created_by: str,
    ) -> IdentityReferenceSet:
        previous = self.repository.get_latest(organization_id, identity_id)
        return self.create_reference_set(
            organization_id=organization_id,
            project_id=previous.project_id,
            brand_id=previous.brand_id,
            identity_type=previous.identity_type,
            name=previous.name,
            canonical_asset_ids=canonical_asset_ids,
            reference_views=reference_views,
            threshold_profile=threshold_profile,
            notes=notes,
            created_at=created_at,
            created_by=created_by,
            privacy_authorized=previous.privacy_authorized,
            identity_id=identity_id,
        )

    def validate(
        self,
        *,
        organization_id: UUID,
        identity_id: UUID,
        candidate: CandidateIdentity,
        profile: ThresholdProfile | None = None,
    ) -> IdentityValidationResult:
        reference = self.repository.get_latest(organization_id, identity_id)
        active_profile = profile or reference.threshold_profile
        bundle = self._bundle(reference, candidate)
        result = self._evaluate(reference, active_profile, bundle, candidate)
        self.repository.save_validation(result)
        return result

    def compare(
        self,
        *,
        organization_id: UUID,
        a: CandidateIdentity,
        b: CandidateIdentity,
        identity_type: IdentityType,
        profile: ThresholdProfile,
        created_at: datetime,
    ) -> IdentityValidationResult:
        if identity_type is IdentityType.FACE:
            raise IdentityPrivacyDenied(
                "FACE pair comparison requires a governed project reference set"
            )
        if a.asset_id is None:
            raise ValueError("IDENTITY_COMPARE_REFERENCE_ASSET_REQUIRED")
        if self.asset_policy is not None:
            self.asset_policy.assert_reference_assets_allowed(
                organization_id,
                (a.asset_id,),
                identity_type=identity_type.value,
            )
        reference_id = new_uuid7()
        payload = {
            "identity_id": str(reference_id),
            "organization_id": str(organization_id),
            "identity_type": identity_type.value,
            "reference_asset_id": str(a.asset_id),
            "profile": profile.model_dump(mode="json"),
        }
        reference = IdentityReferenceSet(
            id=reference_id,
            organization_id=organization_id,
            identity_type=identity_type,
            name="ephemeral-pair-compare",
            canonical_asset_ids=(a.asset_id,),
            reference_views=(ReferenceView(asset_id=a.asset_id, view_key="compare-a"),),
            threshold_profile=profile,
            version=1,
            snapshot_hash=canonical_hash(payload),
            created_at=created_at,
            created_by="identity-engine:pair-compare",
        )
        return self._evaluate(
            reference,
            profile,
            self._bundle(reference, b),
            b,
        )

    def calibrate(
        self,
        *,
        organization_id: UUID,
        identity_type: IdentityType,
        profile_key: str,
        version: int,
        samples: tuple[CalibrationSample, ...],
        target_precision: float,
        created_at: datetime,
    ) -> CalibrationReport:
        report = calibrate_threshold(
            report_id=new_uuid7(),
            organization_id=organization_id,
            identity_type=identity_type,
            profile_key=profile_key,
            version=version,
            samples=samples,
            target_precision=target_precision,
            created_at=created_at,
        )
        self.repository.save_calibration(report)
        return report

    def _bundle(
        self,
        reference: IdentityReferenceSet,
        candidate: CandidateIdentity,
    ) -> SignalBundle:
        if self.signal_provider is None:
            return SignalBundle(
                region=candidate.declared_region,
                signals=(),
                provider_version="unavailable",
            )
        try:
            return self.signal_provider.evaluate(reference, candidate)
        except Exception:
            return SignalBundle(
                region=candidate.declared_region,
                signals=(),
                provider_version="provider-error",
            )

    def _evaluate(
        self,
        reference: IdentityReferenceSet,
        profile: ThresholdProfile,
        bundle: SignalBundle,
        candidate: CandidateIdentity,
    ) -> IdentityValidationResult:
        failures: list[str] = []
        region = bundle.region
        if region is None:
            failures.append("IDENTITY_TARGET_MISSING")
            return self._unavailable(reference, profile, bundle, candidate, failures)
        score, confidence, available_count, coverage = combine_signals(
            reference.identity_type,
            bundle.signals,
            region_quality=region.quality,
            region_confidence=region.detection_confidence,
        )
        if score is None:
            failures.append("IDENTITY_SIGNALS_UNAVAILABLE")
        if available_count < profile.min_signal_count:
            failures.append("IDENTITY_SIGNAL_COUNT_INSUFFICIENT")
        if coverage < 0.5:
            failures.append("IDENTITY_SIGNAL_COVERAGE_LOW")
        if score is None or available_count < profile.min_signal_count:
            return self._unavailable(
                reference, profile, bundle, candidate, failures, confidence=confidence
            )
        if confidence < profile.min_confidence:
            failures.append("IDENTITY_CONFIDENCE_LOW")
        if score < profile.min_score:
            failures.append("IDENTITY_SCORE_BELOW_THRESHOLD")
        if not failures:
            status = IdentityStatus.PASS
        elif profile.severity is IdentitySeverity.HARD:
            status = IdentityStatus.BLOCKED
        elif profile.unavailable_policy is UnavailablePolicy.REVIEW:
            status = IdentityStatus.REVIEW_REQUIRED
        else:
            status = IdentityStatus.WARN
        refs = tuple(
            sorted(
                {
                    *bundle.evidence_refs,
                    *region.evidence_refs,
                    *(ref for signal in bundle.signals for ref in signal.evidence_refs),
                }
            )
        )
        return IdentityValidationResult(
            identity_id=reference.id,
            reference_version=reference.version,
            reference_snapshot_hash=reference.snapshot_hash,
            identity_type=reference.identity_type,
            status=status,
            identity_score=score,
            confidence=confidence,
            threshold_profile=profile,
            signal_scores=bundle.signals,
            region=region,
            evidence_refs=refs,
            failure_codes=tuple(failures),
            provider_version=bundle.provider_version,
            candidate_asset_id=candidate.asset_id,
            candidate_node_id=candidate.node_id,
        )

    def _unavailable(
        self,
        reference: IdentityReferenceSet,
        profile: ThresholdProfile,
        bundle: SignalBundle,
        candidate: CandidateIdentity,
        failures: list[str],
        confidence: float = 0.0,
    ) -> IdentityValidationResult:
        if (
            profile.severity is IdentitySeverity.HARD
            or profile.unavailable_policy is UnavailablePolicy.BLOCK
        ):
            status = IdentityStatus.BLOCKED
        elif profile.unavailable_policy is UnavailablePolicy.REVIEW:
            status = IdentityStatus.REVIEW_REQUIRED
        else:
            status = IdentityStatus.VALIDATION_UNAVAILABLE
        refs = tuple(
            sorted(
                {
                    *bundle.evidence_refs,
                    *(ref for signal in bundle.signals for ref in signal.evidence_refs),
                }
            )
        )
        return IdentityValidationResult(
            identity_id=reference.id,
            reference_version=reference.version,
            reference_snapshot_hash=reference.snapshot_hash,
            identity_type=reference.identity_type,
            status=status,
            identity_score=None,
            confidence=confidence,
            threshold_profile=profile,
            signal_scores=bundle.signals,
            region=bundle.region,
            evidence_refs=refs,
            failure_codes=tuple(failures),
            provider_version=bundle.provider_version,
            candidate_asset_id=candidate.asset_id,
            candidate_node_id=candidate.node_id,
        )
