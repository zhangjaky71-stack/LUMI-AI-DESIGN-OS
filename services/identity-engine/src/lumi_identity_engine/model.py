from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

IdentityType = Literal["PRODUCT", "LOGO", "CHARACTER", "FACE", "STYLE_REFERENCE"]
IdentityScenario = Literal[
    "STRICT_PRESERVE",
    "BACKGROUND_REPLACEMENT",
    "CREATIVE_REDRAW",
    "STYLE_REFERENCE",
]
IdentitySeverity = Literal["HARD", "SOFT", "ADVISORY"]
IdentityStatus = Literal["PASS", "FAIL", "REVIEW", "UNAVAILABLE"]
CalibrationLabel = Literal["POSITIVE", "NEGATIVE", "NEAR_MISS"]


@dataclass(frozen=True)
class IdentityRegion:
    x: float
    y: float
    width: float
    height: float
    coordinate_space: Literal["NORMALIZED", "PIXELS"]


@dataclass(frozen=True)
class FaceReferencePolicy:
    explicit_processing_consent: bool
    purpose: str
    retention_until: str
    persistent_biometric_index: Literal[False] = False


@dataclass(frozen=True)
class IdentityReferenceView:
    view_id: str
    asset_id: str
    asset_version: str
    organization_id: str
    role: str | None = None
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class IdentityReferenceSet:
    identity_id: str
    organization_id: str
    identity_type: IdentityType
    canonical_asset_ids: tuple[str, ...]
    reference_views: tuple[IdentityReferenceView, ...]
    threshold_profile_id: str
    threshold_profile_version: str
    version: str
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
    project_id: str | None = None
    brand_id: str | None = None
    notes: str | None = None
    face_policy: FaceReferencePolicy | None = None


@dataclass(frozen=True)
class VerifiedIdentityAsset:
    asset_id: str
    asset_version: str
    organization_id: str
    checksum_sha256: str
    mime_type: str
    rights: Literal["USER_OWNED", "LICENSED", "UNKNOWN"]
    state: Literal["READY"] = "READY"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationSample:
    sample_id: str
    identity_type: IdentityType
    label: CalibrationLabel
    score: float
    scenario: IdentityScenario
    notes: str | None = None


@dataclass(frozen=True)
class CalibrationMetrics:
    threshold: float
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    false_negative_rate: float
    roc_auc: float
    average_precision: float
    positive_count: int
    negative_count: int
    near_miss_count: int


@dataclass(frozen=True)
class ThresholdCalibrationProfile:
    profile_id: str
    organization_id: str
    identity_type: IdentityType
    scenario: IdentityScenario
    version: str
    threshold: float
    review_floor: float
    minimum_confidence: float
    signal_weights: dict[str, float]
    required_signals: tuple[str, ...]
    model_bundle_version: str
    preprocessor_version: str
    calibration_dataset_version: str
    metrics: CalibrationMetrics
    status: Literal["DRAFT", "PUBLISHED", "RETIRED"] = "PUBLISHED"


@dataclass(frozen=True)
class IdentityEvidenceRef:
    kind: Literal["ASSET", "REGION", "OCR", "FEATURE", "MODEL", "CALIBRATION", "HASH"]
    ref: str
    detail: str | None = None


@dataclass(frozen=True)
class IdentitySignalScore:
    signal: str
    score: float
    confidence: float
    evidence_refs: tuple[IdentityEvidenceRef, ...]
    reference_view_id: str | None = None


@dataclass(frozen=True)
class IdentityCandidate:
    organization_id: str
    artifact_id: str
    artifact_version: str
    checksum_sha256: str | None = None
    ocr_text: str | None = None
    target_region: IdentityRegion | None = None
    target_detected: bool = False
    whole_artifact_target: bool = False
    signal_scores: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class IdentitySignalRequest:
    identity: IdentityReferenceSet
    references: tuple[VerifiedIdentityAsset, ...]
    candidate: IdentityCandidate
    profile: ThresholdCalibrationProfile


class IdentitySignalProvider(Protocol):
    provider_id: str
    provider_version: str
    preprocessor_version: str

    def score(self, request: IdentitySignalRequest) -> tuple[IdentitySignalScore, ...]: ...


@dataclass(frozen=True)
class IdentityValidationReport:
    report_id: str
    organization_id: str
    identity_id: str
    identity_type: IdentityType
    severity: IdentitySeverity
    scenario: IdentityScenario
    status: IdentityStatus
    identity_score: float | None
    confidence: float
    threshold: float
    review_floor: float
    signal_scores: tuple[IdentitySignalScore, ...]
    reference_set_version: str
    threshold_profile_id: str
    threshold_profile_version: str
    calibration_dataset_version: str
    provider_id: str
    provider_version: str
    preprocessor_version: str
    evidence_refs: tuple[IdentityEvidenceRef, ...]
    identity_validation_snapshot_id: str
    candidate_region: IdentityRegion | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class IdentityPrivacyPolicy:
    allow_face_processing: bool = False
    allow_persistent_face_index: Literal[False] = False
    cross_tenant_face_index: Literal[False] = False
