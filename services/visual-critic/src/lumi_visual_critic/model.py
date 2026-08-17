from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class QualityGateStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL_REPAIRABLE = "FAIL_REPAIRABLE"
    FAIL_HARD = "FAIL_HARD"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class QualitySeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    HARD = "HARD"


class QualityDimension(StrEnum):
    CONSTRAINT_COMPLIANCE = "constraint_compliance"
    COMPOSITION = "composition"
    VISUAL_HIERARCHY = "visual_hierarchy"
    ALIGNMENT_SPACING = "alignment_spacing"
    TYPOGRAPHY_READABILITY = "typography_readability"
    CONTRAST = "contrast"
    BRAND_CONSISTENCY = "brand_consistency"
    IDENTITY_CONSISTENCY = "identity_consistency"
    TEXT_ACCURACY = "text_accuracy"
    LOGO_INTEGRITY = "logo_integrity"
    QR_READABILITY = "qr_readability"
    IMAGE_DEFECTS = "image_defects"
    RESOLUTION_EXPORT_READINESS = "resolution_export_readiness"


class EvidenceKind(StrEnum):
    CONSTRAINT_RUNTIME = "constraint_runtime"
    DESIGN_IR = "design_ir"
    OCR = "ocr"
    QR_DECODER = "qr_decoder"
    IDENTITY_ENGINE = "identity_engine"
    BRAND_VALIDATOR = "brand_validator"
    IMAGE_METADATA = "image_metadata"
    VISUAL_GRADER = "visual_grader"
    HUMAN_CALIBRATION = "human_calibration"


class RepairActionType(StrEnum):
    SET_PROPERTY = "SET_PROPERTY"
    MOVE_NODE = "MOVE_NODE"
    RESIZE_NODE = "RESIZE_NODE"
    REPLACE_TEXT = "REPLACE_TEXT"
    REPLACE_ASSET = "REPLACE_ASSET"
    SET_FONT = "SET_FONT"
    SET_COLOR = "SET_COLOR"
    SET_SPACING = "SET_SPACING"
    REGENERATE_REGION = "REGENERATE_REGION"
    REGENERATE_ASSET = "REGENERATE_ASSET"


class QualityProfileKey(StrEnum):
    EXPLORATION = "exploration"
    PRODUCTION_WEB = "production-web"
    BRAND_STRICT = "brand-strict"
    PRODUCT_STRICT = "product-strict"
    PRINT = "print"
    SOCIAL_FAST = "social-fast"


@dataclass(frozen=True, slots=True)
class QualityEvidence:
    evidence_id: str
    kind: EvidenceKind
    source_version: str
    summary: str
    refs: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.source_version or not self.summary:
            raise ValueError("QUALITY_EVIDENCE_IDENTITY_REQUIRED")


@dataclass(frozen=True, slots=True)
class RepairAction:
    action_type: RepairActionType
    target: str
    reason_code: str
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_effect: tuple[QualityDimension, ...] = ()

    def __post_init__(self) -> None:
        if not self.target or not self.reason_code:
            raise ValueError("QUALITY_REPAIR_ACTION_IDENTITY_REQUIRED")
        if self.action_type is RepairActionType.SET_PROPERTY and "property" not in self.parameters:
            raise ValueError("QUALITY_SET_PROPERTY_REQUIRES_PROPERTY")
        if self.action_type is RepairActionType.REPLACE_TEXT and "text" not in self.parameters:
            raise ValueError("QUALITY_REPLACE_TEXT_REQUIRES_TEXT")


@dataclass(frozen=True, slots=True)
class QualityViolation:
    violation_id: str
    dimension: QualityDimension
    code: str
    severity: QualitySeverity
    message: str
    confidence: float
    blocking: bool = False
    evidence_ids: tuple[str, ...] = ()
    repair_actions: tuple[RepairAction, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("QUALITY_VIOLATION_CONFIDENCE_INVALID")
        if self.severity is QualitySeverity.HARD and not self.blocking:
            raise ValueError("QUALITY_HARD_VIOLATION_MUST_BLOCK")


@dataclass(frozen=True, slots=True)
class DimensionAssessment:
    dimension: QualityDimension
    score: float
    confidence: float
    threshold: float
    severity: QualitySeverity
    evidence_ids: tuple[str, ...] = ()
    grader_id: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100 or not 0 <= self.threshold <= 100:
            raise ValueError("QUALITY_DIMENSION_SCORE_INVALID")
        if not 0 <= self.confidence <= 1:
            raise ValueError("QUALITY_DIMENSION_CONFIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class GraderCalibrationSnapshot:
    calibration_id: str
    grader_id: str
    provider: str | None
    model: str | None
    model_revision: str | None
    dataset_hash: str
    threshold_version: int
    sample_count: int
    precision: float | None = None
    recall: float | None = None
    false_positive_rate: float | None = None
    false_negative_rate: float | None = None
    inter_rater_agreement: float | None = None

    def __post_init__(self) -> None:
        _sha256(self.dataset_hash, "grader dataset hash")
        if self.threshold_version < 1 or self.sample_count < 1:
            raise ValueError("QUALITY_GRADER_CALIBRATION_INVALID")
        for value in (
            self.precision,
            self.recall,
            self.false_positive_rate,
            self.false_negative_rate,
            self.inter_rater_agreement,
        ):
            if value is not None and not 0 <= value <= 1:
                raise ValueError("QUALITY_GRADER_CALIBRATION_METRIC_INVALID")

    def semantic_hash(self) -> str:
        return _canonical_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class QualityProfileSnapshot:
    profile_id: str
    key: QualityProfileKey
    version: int
    weights: dict[QualityDimension, float]
    thresholds: dict[QualityDimension, float]
    overall_pass_threshold: float
    warning_threshold: float
    low_confidence_threshold: float
    hard_dimensions: frozenset[QualityDimension]
    required_dimensions: frozenset[QualityDimension]
    visual_grader_required: bool = True

    def __post_init__(self) -> None:
        if self.version < 1 or not self.profile_id:
            raise ValueError("QUALITY_PROFILE_IDENTITY_REQUIRED")
        if not self.weights or sum(self.weights.values()) <= 0:
            raise ValueError("QUALITY_PROFILE_WEIGHTS_INVALID")
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("QUALITY_PROFILE_WEIGHTS_INVALID")
        if set(self.weights) != set(self.thresholds):
            raise ValueError("QUALITY_PROFILE_DIMENSIONS_MISMATCH")
        if not self.required_dimensions <= set(self.weights):
            raise ValueError("QUALITY_PROFILE_REQUIRED_DIMENSION_UNKNOWN")
        for value in (
            self.overall_pass_threshold,
            self.warning_threshold,
        ):
            if not 0 <= value <= 100:
                raise ValueError("QUALITY_PROFILE_THRESHOLD_INVALID")
        if not 0 <= self.low_confidence_threshold <= 1:
            raise ValueError("QUALITY_PROFILE_CONFIDENCE_INVALID")

    def semantic_hash(self) -> str:
        return _canonical_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class ArtifactQualityInput:
    organization_id: str
    project_id: str
    artifact_id: str
    artifact_version_id: str
    artifact_type: str
    content_hash: str
    primary_file_ref: str
    metadata: dict[str, Any] = field(default_factory=dict)
    design_ir_ref: str | None = None
    brand_rule_snapshot_id: str | None = None
    identity_refs: tuple[str, ...] = ()
    generation_provider: str | None = None
    generation_model: str | None = None
    generation_model_revision: str | None = None

    def __post_init__(self) -> None:
        _sha256(self.content_hash, "artifact content hash")
        if not all(
            (
                self.organization_id,
                self.project_id,
                self.artifact_id,
                self.artifact_version_id,
                self.artifact_type,
                self.primary_file_ref,
            )
        ):
            raise ValueError("QUALITY_ARTIFACT_INPUT_IDENTITY_REQUIRED")


@dataclass(frozen=True, slots=True)
class QualityTaskSpec:
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    artifact_version_id: str
    profile: QualityProfileSnapshot
    requested_by: str
    critic_calibration: GraderCalibrationSnapshot | None = None

    def __post_init__(self) -> None:
        if not all(
            (
                self.organization_id,
                self.project_id,
                self.task_id,
                self.operation_id,
                self.artifact_version_id,
                self.requested_by,
            )
        ):
            raise ValueError("QUALITY_TASK_IDENTITY_REQUIRED")
        if self.profile.visual_grader_required and self.critic_calibration is None:
            raise ValueError("QUALITY_CRITIC_CALIBRATION_REQUIRED")

    def semantic_hash(self) -> str:
        return _canonical_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class QualitySignalBundle:
    source_id: str
    deterministic: bool
    assessments: tuple[DimensionAssessment, ...]
    violations: tuple[QualityViolation, ...]
    evidence: tuple[QualityEvidence, ...]
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class VisualGraderResult:
    grader_id: str
    calibration_id: str
    assessments: tuple[DimensionAssessment, ...]
    violations: tuple[QualityViolation, ...]
    evidence: tuple[QualityEvidence, ...]
    strengths: tuple[str, ...]
    overall_confidence: float

    def __post_init__(self) -> None:
        if not 0 <= self.overall_confidence <= 1:
            raise ValueError("QUALITY_VISUAL_GRADER_CONFIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class QualityResult:
    quality_result_id: str
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    artifact_id: str
    artifact_version_id: str
    artifact_content_hash: str
    profile_id: str
    profile_version: int
    profile_hash: str
    status: QualityGateStatus
    overall_score: float
    overall_confidence: float
    assessments: tuple[DimensionAssessment, ...]
    violations: tuple[QualityViolation, ...]
    evidence: tuple[QualityEvidence, ...]
    strengths: tuple[str, ...]
    repair_actions: tuple[RepairAction, ...]
    critic_grader_id: str | None
    critic_calibration_id: str | None
    critic_calibration_hash: str | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.overall_score <= 100:
            raise ValueError("QUALITY_RESULT_SCORE_INVALID")
        if not 0 <= self.overall_confidence <= 1:
            raise ValueError("QUALITY_RESULT_CONFIDENCE_INVALID")
        _sha256(self.artifact_content_hash, "quality artifact content hash")
        _sha256(self.profile_hash, "quality profile hash")
        if self.critic_calibration_hash is not None:
            _sha256(self.critic_calibration_hash, "critic calibration hash")
        if self.status is QualityGateStatus.FAIL_HARD and not any(
            violation.blocking for violation in self.violations
        ):
            raise ValueError("QUALITY_FAIL_HARD_REQUIRES_BLOCKING_VIOLATION")


def _sha256(value: str, label: str) -> None:
    if len(value) != 64 or value.lower() != value:
        raise ValueError(f"{label} must be lowercase sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be lowercase sha256") from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, frozenset):
        return sorted(item.value if isinstance(item, StrEnum) else item for item in value)
    if isinstance(value, dict):
        return {
            str(key.value if isinstance(key, StrEnum) else key): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
