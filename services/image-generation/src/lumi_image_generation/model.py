from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID


class GenerationMode(StrEnum):
    TEXT_TO_IMAGE = "TEXT_TO_IMAGE"
    REFERENCE_TO_IMAGE = "REFERENCE_TO_IMAGE"
    PRODUCT_SCENE = "PRODUCT_SCENE"
    STYLE_REFERENCE = "STYLE_REFERENCE"
    TRANSPARENT_ASSET = "TRANSPARENT_ASSET"
    BACKGROUND_GENERATION = "BACKGROUND_GENERATION"
    COMPOSITION_EXPLORATION = "COMPOSITION_EXPLORATION"


class ReferenceRole(StrEnum):
    IDENTITY = "IDENTITY"
    STYLE = "STYLE"
    COMPOSITION = "COMPOSITION"
    CONTENT = "CONTENT"


class ReferenceSource(StrEnum):
    USER_EXPLICIT = "USER_EXPLICIT"
    ASSET_RESOLVER = "ASSET_RESOLVER"
    RECIPE = "RECIPE"
    BRAND_PROFILE = "BRAND_PROFILE"


class ConstraintSeverity(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"
    ADVISORY = "ADVISORY"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PROVIDER_PENDING = "PROVIDER_PENDING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CandidateStatus(StrEnum):
    QUEUED = "QUEUED"
    PROVIDER_PENDING = "PROVIDER_PENDING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GatewayStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PENDING = "PENDING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class QualityProfile(StrEnum):
    DRAFT = "DRAFT"
    BALANCED = "BALANCED"
    HIGH = "HIGH"
    MAX = "MAX"


class OutputFormat(StrEnum):
    PNG = "PNG"
    JPEG = "JPEG"
    WEBP = "WEBP"


def _canonical(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("GENERATION_NON_FINITE_DECIMAL")
        return format(value, "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("GENERATION_NON_FINITE_FLOAT")
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonical(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        _canonical(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ImageReference:
    asset_id: UUID
    asset_version: str
    role: ReferenceRole
    source: ReferenceSource
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.asset_version.strip():
            raise ValueError("IMAGE_REFERENCE_VERSION_REQUIRED")
        if self.note is not None and len(self.note) > 1000:
            raise ValueError("IMAGE_REFERENCE_NOTE_TOO_LONG")


@dataclass(frozen=True, slots=True)
class AuthorizedReference:
    asset_id: UUID
    asset_version: str
    role: ReferenceRole
    source: ReferenceSource
    durable_ref: str
    rights_level: str
    commercial_use: bool
    checksum_sha256: str
    mime_type: str
    approval_state: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.durable_ref or "://" in self.durable_ref:
            raise ValueError("AUTHORIZED_REFERENCE_DURABLE_REF_REQUIRED")
        if len(self.checksum_sha256) != 64:
            raise ValueError("AUTHORIZED_REFERENCE_CHECKSUM_INVALID")


@dataclass(frozen=True, slots=True)
class IdentityRequirement:
    identity_id: UUID
    reference_set_version: str
    severity: ConstraintSeverity
    scenario: str

    def __post_init__(self) -> None:
        if not self.reference_set_version or not self.scenario:
            raise ValueError("IDENTITY_REQUIREMENT_INCOMPLETE")


@dataclass(frozen=True, slots=True)
class GenerationConstraint:
    constraint_id: str
    constraint_type: str
    severity: ConstraintSeverity
    snapshot_hash: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.constraint_id or not self.constraint_type:
            raise ValueError("GENERATION_CONSTRAINT_INCOMPLETE")
        if len(self.snapshot_hash) != 64:
            raise ValueError("GENERATION_CONSTRAINT_SNAPSHOT_INVALID")
        _canonical(self.parameters)


@dataclass(frozen=True, slots=True)
class OutputRequirements:
    format: OutputFormat = OutputFormat.PNG
    transparent_background: bool = False
    exact_dimensions: bool = True
    minimum_width: int | None = None
    minimum_height: int | None = None

    def __post_init__(self) -> None:
        if self.transparent_background and self.format is not OutputFormat.PNG:
            raise ValueError("TRANSPARENT_OUTPUT_REQUIRES_PNG")
        for value in (self.minimum_width, self.minimum_height):
            if value is not None and value <= 0:
                raise ValueError("IMAGE_OUTPUT_MIN_DIMENSION_INVALID")


@dataclass(frozen=True, slots=True)
class PromptBlocks:
    objective: str
    content: str
    visual_direction: str
    brand_constraints: tuple[str, ...]
    identity_requirements: tuple[str, ...]
    negative_constraints: tuple[str, ...]
    output_dimensions: str
    template_version: str

    @property
    def prompt_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True, slots=True)
class ImageGenerationSpec:
    organization_id: UUID
    project_id: UUID
    task_id: UUID
    operation_id: UUID
    purpose: str
    mode: GenerationMode
    prompt_compilation_ref: str
    objective: str
    content: str
    visual_direction: str
    aspect_ratio: str
    target_width: int
    target_height: int
    variant_count: int
    references: tuple[ImageReference, ...]
    identity_requirements: tuple[IdentityRequirement, ...]
    brand_rule_set_version: str | None
    constraints: tuple[GenerationConstraint, ...]
    quality_profile: QualityProfile
    budget_limit_usd: Decimal
    output_requirements: OutputRequirements
    code_git_sha: str
    agent_run_id: UUID | None = None
    agent_version: str | None = None
    recipe_version: str | None = None
    skill_versions: Mapping[str, str] = field(default_factory=dict)
    seed: int | None = None
    user_intent_ref: str | None = None
    user_use_declaration: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.purpose,
            self.prompt_compilation_ref,
            self.objective,
            self.content,
            self.aspect_ratio,
        )
        if any(not value.strip() for value in required):
            raise ValueError("GENERATION_TEXT_FIELD_REQUIRED")
        if self.target_width <= 0 or self.target_height <= 0:
            raise ValueError("GENERATION_TARGET_DIMENSIONS_INVALID")
        if self.target_width > 16384 or self.target_height > 16384:
            raise ValueError("GENERATION_TARGET_DIMENSIONS_EXCESSIVE")
        if not 1 <= self.variant_count <= 16:
            raise ValueError("GENERATION_VARIANT_COUNT_INVALID")
        if isinstance(self.budget_limit_usd, float):
            raise ValueError("GENERATION_BUDGET_FLOAT_FORBIDDEN")
        if not self.budget_limit_usd.is_finite() or self.budget_limit_usd < 0:
            raise ValueError("GENERATION_BUDGET_INVALID")
        if len(self.references) > 32 or len(self.constraints) > 128:
            raise ValueError("GENERATION_INPUT_LIMIT")
        if len(self.identity_requirements) > 16:
            raise ValueError("GENERATION_IDENTITY_REQUIREMENT_LIMIT")
        if len(self.code_git_sha) != 40:
            raise ValueError("GENERATION_GIT_SHA_INVALID")
        if any(ch not in "0123456789abcdef" for ch in self.code_git_sha):
            raise ValueError("GENERATION_GIT_SHA_INVALID")
        if self.seed is not None and not 0 <= self.seed <= 2**63 - 1:
            raise ValueError("GENERATION_SEED_INVALID")
        _canonical(self.skill_versions)

    @property
    def semantic_hash(self) -> str:
        payload = asdict(self)
        payload.pop("operation_id")
        payload.pop("code_git_sha")
        return canonical_hash(payload)

    @property
    def hard_constraint_snapshot_hash(self) -> str:
        snapshots = sorted(
            item.snapshot_hash
            for item in self.constraints
            if item.severity is ConstraintSeverity.HARD
        )
        return canonical_hash(snapshots)


@dataclass(frozen=True, slots=True)
class VariantDecision:
    requested_count: int
    selected_count: int
    estimated_cost_per_variant_usd: Decimal
    estimated_total_usd: Decimal
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    request_id: UUID
    organization_id: UUID
    project_id: UUID
    task_id: UUID
    root_operation_id: UUID
    variant_operation_id: UUID
    generation_id: UUID
    variant_index: int
    mode: GenerationMode
    prompt: PromptBlocks
    references: tuple[AuthorizedReference, ...]
    target_width: int
    target_height: int
    quality_profile: QualityProfile
    budget_limit_usd: Decimal
    constraints: tuple[GenerationConstraint, ...]
    output_requirements: OutputRequirements
    seed: int | None
    agent_run_id: UUID | None


@dataclass(frozen=True, slots=True)
class ProviderOutputRef:
    ref: str
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class GatewayResult:
    status: GatewayStatus
    provider: str
    model: str
    outputs: tuple[ProviderOutputRef, ...] = ()
    provider_request_id: str | None = None
    model_revision: str | None = None
    registry_snapshot_id: str | None = None
    cost_usd: Decimal | None = None
    cost_confidence: str = "unknown"
    pricing_snapshot_id: str | None = None
    routing_reason_codes: tuple[str, ...] = ()
    safety_metadata: Mapping[str, object] = field(default_factory=dict)
    finish_reason: str | None = None
    seed: int | None = None


@dataclass(frozen=True, slots=True)
class FetchedImage:
    source_ref: str
    content: bytes
    declared_mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    content: bytes
    mime_type: str
    width: int
    height: int
    checksum_sha256: str
    has_alpha: bool


@dataclass(frozen=True, slots=True)
class StoredImage:
    bucket: str
    storage_key: str
    mime_type: str
    width: int
    height: int
    size_bytes: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        if not self.bucket or not self.storage_key or "://" in self.storage_key:
            raise ValueError("GENERATION_STORAGE_LOCATION_INVALID")


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    validator: str
    status: ValidationStatus
    severity: ConstraintSeverity
    reason_code: str
    score: float | None = None
    threshold: float | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationBundle:
    findings: tuple[ValidationFinding, ...]
    identity_validation_snapshot_id: str | None = None
    brand_validation_snapshot_id: str | None = None

    @property
    def hard_failed(self) -> bool:
        return any(
            item.severity is ConstraintSeverity.HARD
            and item.status in {ValidationStatus.FAIL, ValidationStatus.UNAVAILABLE}
            for item in self.findings
        )


@dataclass(frozen=True, slots=True)
class GenerationProvenance:
    generation_id: UUID
    organization_id: UUID
    project_id: UUID
    task_id: UUID
    operation_id: UUID
    variant_operation_id: UUID
    variant_index: int
    provider: str
    model: str
    model_revision: str | None
    registry_snapshot_id: str | None
    provider_request_id: str | None
    prompt_hash: str
    prompt_template_version: str
    prompt_compilation_ref: str
    reference_asset_ids: tuple[UUID, ...]
    reference_asset_versions: tuple[str, ...]
    seed: int | None
    width: int
    height: int
    quality_profile: QualityProfile
    routing_reason_codes: tuple[str, ...]
    pricing_snapshot_id: str | None
    cost_usd: Decimal | None
    cost_confidence: str
    agent_run_id: UUID | None
    agent_version: str | None
    recipe_version: str | None
    skill_versions: Mapping[str, str]
    code_git_sha: str
    constraint_snapshot_hash: str
    brand_rule_set_version: str | None
    identity_validation_snapshot_id: str | None
    brand_validation_snapshot_id: str | None
    safety_metadata: Mapping[str, object]
    user_use_declaration: str | None

    @property
    def snapshot_id(self) -> str:
        return f"image-generation-provenance:{canonical_hash(self)}"


@dataclass(frozen=True, slots=True)
class GenerationCandidate:
    candidate_id: UUID
    generation_id: UUID
    variant_index: int
    variant_operation_id: UUID
    status: CandidateStatus
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    model_revision: str | None = None
    registry_snapshot_id: str | None = None
    stored_image: StoredImage | None = None
    artifact_id: UUID | None = None
    artifact_version_id: UUID | None = None
    validation: ValidationBundle | None = None
    provenance_snapshot_id: str | None = None
    cost_usd: Decimal | None = None
    cost_confidence: str | None = None
    pricing_snapshot_id: str | None = None
    routing_reason_codes: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationJob:
    generation_id: UUID
    organization_id: UUID
    project_id: UUID
    task_id: UUID
    operation_id: UUID
    semantic_hash: str
    status: JobStatus
    prompt_hash: str
    prompt: PromptBlocks
    authorized_references: tuple[AuthorizedReference, ...]
    variant_decision: VariantDecision
    candidates: tuple[GenerationCandidate, ...]
    created_at: str
    updated_at: str
    completed_at: str | None = None
    error_code: str | None = None
