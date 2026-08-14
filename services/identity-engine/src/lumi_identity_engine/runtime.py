from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict

from .model import (
    IdentityCandidate,
    IdentityEvidenceRef,
    IdentityPrivacyPolicy,
    IdentityReferenceSet,
    IdentitySeverity,
    IdentitySignalRequest,
    IdentitySignalScore,
    IdentityValidationReport,
    IdentityScenario,
    ThresholdCalibrationProfile,
    VerifiedIdentityAsset,
)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _token_similarity(left: str, right: str) -> float:
    a = {item for item in _normalize_text(left).replace("/", " ").split() if item}
    b = {item for item in _normalize_text(right).replace("/", " ").split() if item}
    if not a and not b:
        return 100.0
    union = a | b
    return 100.0 * len(a & b) / len(union) if union else 0.0


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


class StructuredIdentitySignalProvider:
    def __init__(self, provider_id: str, provider_version: str, preprocessor_version: str) -> None:
        self.provider_id = provider_id
        self.provider_version = provider_version
        self.preprocessor_version = preprocessor_version

    def score(self, request: IdentitySignalRequest) -> tuple[IdentitySignalScore, ...]:
        scores: list[IdentitySignalScore] = []
        for signal, raw in request.candidate.signal_scores.items():
            score: float | None = None
            confidence = 1.0
            evidence_ref = f"structured:{signal}"
            if isinstance(raw, int | float):
                score = float(raw)
            elif isinstance(raw, dict):
                raw_score = raw.get("score")
                raw_confidence = raw.get("confidence")
                raw_evidence = raw.get("evidence_ref")
                if isinstance(raw_score, int | float):
                    score = float(raw_score)
                if isinstance(raw_confidence, int | float):
                    confidence = max(0.0, min(1.0, float(raw_confidence)))
                if isinstance(raw_evidence, str):
                    evidence_ref = raw_evidence
            if score is not None:
                scores.append(
                    IdentitySignalScore(
                        signal=signal,
                        score=_clamp_score(score),
                        confidence=confidence,
                        evidence_refs=(IdentityEvidenceRef("MODEL", evidence_ref),),
                    )
                )

        checksum = request.candidate.checksum_sha256
        if checksum:
            matched = next(
                (item for item in request.references if item.checksum_sha256 == checksum), None
            )
            reference_view_id = None
            if matched:
                view = next(
                    (
                        item
                        for item in request.identity.reference_views
                        if item.asset_id == matched.asset_id
                        and item.asset_version == matched.asset_version
                    ),
                    None,
                )
                reference_view_id = view.view_id if view else None
            scores.append(
                IdentitySignalScore(
                    signal="exact_hash",
                    score=100.0 if matched else 0.0,
                    confidence=1.0,
                    reference_view_id=reference_view_id,
                    evidence_refs=(
                        IdentityEvidenceRef(
                            "HASH",
                            f"sha256:{checksum}",
                            "exact canonical asset match" if matched else "no canonical checksum match",
                        ),
                    ),
                )
            )

        if request.candidate.ocr_text:
            reference_texts = tuple(
                value
                for reference in request.references
                if isinstance((value := reference.metadata.get("ocr_text")), str)
            )
            if reference_texts:
                best = max(
                    _token_similarity(request.candidate.ocr_text, reference)
                    for reference in reference_texts
                )
                scores.append(
                    IdentitySignalScore(
                        signal="ocr_wordmark",
                        score=best,
                        confidence=0.95,
                        evidence_refs=(
                            IdentityEvidenceRef(
                                "OCR", f"ocr:{_normalize_text(request.candidate.ocr_text)}"
                            ),
                        ),
                    )
                )
        return tuple(sorted(scores, key=lambda item: (item.signal, -item.score)))


def _assert_face_privacy(
    reference_set: IdentityReferenceSet, policy: IdentityPrivacyPolicy
) -> None:
    if reference_set.identity_type != "FACE":
        return
    if not policy.allow_face_processing:
        raise ValueError("FACE_PROCESSING_NOT_ALLOWED")
    if policy.allow_persistent_face_index or policy.cross_tenant_face_index:
        raise ValueError("FACE_INDEX_POLICY_INVALID")
    face_policy = reference_set.face_policy
    if face_policy is None or not face_policy.explicit_processing_consent:
        raise ValueError("FACE_EXPLICIT_CONSENT_REQUIRED")
    if not face_policy.purpose.strip():
        raise ValueError("FACE_PROCESSING_PURPOSE_REQUIRED")
    if face_policy.persistent_biometric_index is not False:
        raise ValueError("PERSISTENT_FACE_INDEX_FORBIDDEN")


def _validate_profile(
    identity: IdentityReferenceSet,
    profile: ThresholdCalibrationProfile,
    provider: StructuredIdentitySignalProvider,
) -> None:
    if identity.status != "PUBLISHED" or profile.status != "PUBLISHED":
        raise ValueError("IDENTITY_PROFILE_NOT_PUBLISHED")
    if identity.organization_id != profile.organization_id:
        raise ValueError("IDENTITY_PROFILE_TENANT_MISMATCH")
    if identity.identity_type != profile.identity_type:
        raise ValueError("IDENTITY_PROFILE_TYPE_MISMATCH")
    if (
        identity.threshold_profile_id != profile.profile_id
        or identity.threshold_profile_version != profile.version
    ):
        raise ValueError("IDENTITY_PROFILE_VERSION_MISMATCH")
    if profile.model_bundle_version != provider.provider_version:
        raise ValueError("IDENTITY_PROVIDER_VERSION_MISMATCH")
    if profile.preprocessor_version != provider.preprocessor_version:
        raise ValueError("IDENTITY_PREPROCESSOR_VERSION_MISMATCH")
    if identity.identity_type in {"PRODUCT", "LOGO"} and len(set(profile.required_signals)) < 2:
        raise ValueError("IDENTITY_MULTI_SIGNAL_PROFILE_REQUIRED")


def _validate_references(
    identity: IdentityReferenceSet, references: tuple[VerifiedIdentityAsset, ...]
) -> None:
    if not identity.reference_views or not identity.canonical_asset_ids:
        raise ValueError("IDENTITY_REFERENCE_SET_EMPTY")
    view_keys = {f"{item.asset_id}@{item.asset_version}" for item in identity.reference_views}
    resolved: set[str] = set()
    for reference in references:
        if reference.organization_id != identity.organization_id:
            raise ValueError("IDENTITY_REFERENCE_TENANT_MISMATCH")
        if f"{reference.asset_id}@{reference.asset_version}" not in view_keys:
            raise ValueError("IDENTITY_REFERENCE_VERSION_MISMATCH")
        resolved.add(reference.asset_id)
    for asset_id in identity.canonical_asset_ids:
        if asset_id not in resolved:
            raise ValueError(f"IDENTITY_CANONICAL_ASSET_UNRESOLVED:{asset_id}")


def _validate_target(identity: IdentityReferenceSet, candidate: IdentityCandidate) -> None:
    if identity.identity_type == "STYLE_REFERENCE":
        return
    if candidate.target_region or candidate.target_detected or candidate.whole_artifact_target:
        return
    raise ValueError("IDENTITY_TARGET_REGION_UNAVAILABLE")


def _select_scores(scores: tuple[IdentitySignalScore, ...]) -> dict[str, IdentitySignalScore]:
    selected: dict[str, IdentitySignalScore] = {}
    for row in scores:
        if not 0 <= row.score <= 100 or not 0 <= row.confidence <= 1:
            raise ValueError("IDENTITY_SIGNAL_INVALID")
        existing = selected.get(row.signal)
        if existing is None or (row.score, row.confidence) > (existing.score, existing.confidence):
            selected[row.signal] = row
    return selected


def _aggregate(
    selected: dict[str, IdentitySignalScore], profile: ThresholdCalibrationProfile
) -> tuple[float, float]:
    weighted_score = weighted_confidence = total_weight = 0.0
    for signal, weight in sorted(profile.signal_weights.items()):
        row = selected.get(signal)
        if row is None:
            continue
        if weight <= 0:
            raise ValueError(f"IDENTITY_SIGNAL_WEIGHT_INVALID:{signal}")
        weighted_score += row.score * weight
        weighted_confidence += row.confidence * weight
        total_weight += weight
    if total_weight == 0:
        raise ValueError("IDENTITY_NO_WEIGHTED_SIGNALS")
    return weighted_score / total_weight, weighted_confidence / total_weight


class IdentityValidationRuntime:
    def __init__(
        self,
        provider: StructuredIdentitySignalProvider,
        privacy_policy: IdentityPrivacyPolicy | None = None,
    ) -> None:
        self.provider = provider
        self.privacy_policy = privacy_policy or IdentityPrivacyPolicy()

    def validate(
        self,
        *,
        identity: IdentityReferenceSet,
        profile: ThresholdCalibrationProfile,
        candidate: IdentityCandidate,
        references: tuple[VerifiedIdentityAsset, ...],
        severity: IdentitySeverity,
        scenario: IdentityScenario,
    ) -> IdentityValidationReport:
        if identity.organization_id != candidate.organization_id:
            raise ValueError("IDENTITY_CANDIDATE_TENANT_MISMATCH")
        if profile.scenario != scenario:
            raise ValueError("IDENTITY_SCENARIO_PROFILE_MISMATCH")
        if identity.identity_type == "STYLE_REFERENCE" and severity == "HARD":
            raise ValueError("STYLE_REFERENCE_CANNOT_BE_HARD")
        _assert_face_privacy(identity, self.privacy_policy)
        _validate_profile(identity, profile, self.provider)
        _validate_references(identity, references)
        _validate_target(identity, candidate)

        selected = _select_scores(
            self.provider.score(IdentitySignalRequest(identity, references, candidate, profile))
        )
        missing = sorted(signal for signal in profile.required_signals if signal not in selected)
        if missing:
            raise ValueError(f"IDENTITY_REQUIRED_SIGNAL_UNAVAILABLE:{','.join(missing)}")
        if identity.identity_type in {"PRODUCT", "LOGO"} and len(selected) < 2:
            raise ValueError("IDENTITY_MULTI_SIGNAL_EVIDENCE_REQUIRED")
        identity_score, confidence = _aggregate(selected, profile)
        if confidence < profile.minimum_confidence:
            status = "REVIEW"
            reason = "IDENTITY_CONFIDENCE_BELOW_MINIMUM"
        elif identity_score >= profile.threshold:
            status = "PASS"
            reason = None
        elif identity_score >= profile.review_floor:
            status = "REVIEW"
            reason = "IDENTITY_REVIEW_REQUIRED"
        else:
            status = "FAIL"
            reason = "IDENTITY_SCORE_BELOW_THRESHOLD"

        ordered_scores = tuple(selected[key] for key in sorted(selected))
        snapshot_payload = {
            "identity_id": identity.identity_id,
            "reference_set_version": identity.version,
            "threshold_profile_id": profile.profile_id,
            "threshold_profile_version": profile.version,
            "calibration_dataset_version": profile.calibration_dataset_version,
            "provider_id": self.provider.provider_id,
            "provider_version": self.provider.provider_version,
            "preprocessor_version": self.provider.preprocessor_version,
            "signals": [
                {
                    "signal": row.signal,
                    "score": row.score,
                    "confidence": row.confidence,
                    "reference_view_id": row.reference_view_id,
                }
                for row in ordered_scores
            ],
        }
        snapshot_id = f"identity-validation:{_canonical_hash(snapshot_payload)}"
        report_payload = {
            "identity_validation_snapshot_id": snapshot_id,
            "artifact_id": candidate.artifact_id,
            "artifact_version": candidate.artifact_version,
            "target_region": asdict(candidate.target_region) if candidate.target_region else None,
            "identity_score": identity_score,
            "confidence": confidence,
            "status": status,
            "severity": severity,
        }
        evidence: list[IdentityEvidenceRef] = [
            IdentityEvidenceRef(
                "CALIBRATION",
                f"{profile.calibration_dataset_version}:{profile.profile_id}@{profile.version}",
            )
        ]
        for row in ordered_scores:
            evidence.extend(row.evidence_refs)
        deduped = {
            (item.kind, item.ref, item.detail): item
            for item in evidence
        }
        return IdentityValidationReport(
            report_id=f"identity-report:{_canonical_hash(report_payload)}",
            organization_id=identity.organization_id,
            identity_id=identity.identity_id,
            identity_type=identity.identity_type,
            severity=severity,
            scenario=scenario,
            status=status,
            identity_score=identity_score,
            confidence=confidence,
            threshold=profile.threshold,
            review_floor=profile.review_floor,
            signal_scores=ordered_scores,
            reference_set_version=identity.version,
            threshold_profile_id=profile.profile_id,
            threshold_profile_version=profile.version,
            calibration_dataset_version=profile.calibration_dataset_version,
            provider_id=self.provider.provider_id,
            provider_version=self.provider.provider_version,
            preprocessor_version=self.provider.preprocessor_version,
            evidence_refs=tuple(
                deduped[key] for key in sorted(deduped, key=lambda row: (row[0], row[1], row[2] or ""))
            ),
            identity_validation_snapshot_id=snapshot_id,
            candidate_region=candidate.target_region,
            reason_code=reason,
        )


def identity_validation_batch_snapshot_id(
    reports: tuple[IdentityValidationReport, ...],
) -> str:
    if not reports:
        raise ValueError("IDENTITY_VALIDATION_BATCH_EMPTY")
    if len({report.organization_id for report in reports}) != 1:
        raise ValueError("IDENTITY_VALIDATION_BATCH_TENANT_MISMATCH")
    payload = [
        {
            "report_id": report.report_id,
            "identity_id": report.identity_id,
            "status": report.status,
            "severity": report.severity,
            "identity_validation_snapshot_id": report.identity_validation_snapshot_id,
        }
        for report in sorted(reports, key=lambda row: (row.identity_id, row.report_id))
    ]
    return f"identity-batch:{_canonical_hash(payload)}"
