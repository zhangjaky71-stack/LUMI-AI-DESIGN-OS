from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal
from typing import Any, Literal, Mapping
from uuid import UUID

GenerationMode = Literal[
    "TEXT_TO_IMAGE",
    "REFERENCE_TO_IMAGE",
    "PRODUCT_SCENE",
    "STYLE_REFERENCE",
    "TRANSPARENT_ASSET",
    "BACKGROUND_GENERATION",
    "COMPOSITION_EXPLORATION",
]
ReferenceRole = Literal["IDENTITY", "STYLE", "COMPOSITION", "CONTENT"]
ReferenceSource = Literal["USER_EXPLICIT", "ASSET_RESOLVER", "RECIPE", "BRAND_PROFILE"]
Rights = Literal["USER_OWNED", "LICENSED", "UNKNOWN"]
ConstraintSeverity = Literal["HARD", "SOFT", "ADVISORY"]
GenerationJobStatus = Literal[
    "PENDING",
    "RUNNING",
    "PROVIDER_PENDING",
    "VALIDATING",
    "COMPLETED",
    "PARTIAL",
    "FAILED",
]
CandidateStatus = Literal["PROVIDER_PENDING", "VALIDATING", "READY", "REJECTED", "FAILED"]
GatewayResultStatus = Literal["SUCCEEDED", "PENDING", "FAILED", "CANCELLED"]
ValidationStatus = Literal["PASS", "WARN", "FAIL", "UNAVAILABLE"]
QualityProfile = Literal["DRAFT", "BALANCED", "HIGH", "MAX"]
OutputFormat = Literal["PNG", "JPEG", "WEBP"]


def _require_nonblank(value: str, code: str) -> None:
    if not value.strip():
        raise ValueError(code)


def _require_uuid(value: str, code: str) -> None:
    try:
        UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(code) from exc


def _require_sha256(value: str, code: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(code)


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_normalize(item) for item in value]
    if isinstance(value, bool | int | str) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("GENERATION_NON_FINITE_FLOAT")
        return value
    raise ValueError(f"GENERATION_UNSUPPORTED_CANONICAL_VALUE:{type(value).__name__}")


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        _normalize(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ImageReference:
    asset_id: str
    asset_version: str
    role: ReferenceRole
    source: ReferenceSource
    note: str | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.asset_id, "IMAGE_REFERENCE_ASSET_ID_REQUIRED")
        _require_nonblank(self.asset_version, "IMAGE_REFERENCE_VERSION_REQUIRED")
        if self.note is not None and len(self.note) > 1000:
            raise ValueError("IMAGE_REFERENCE_NOTE_TOO_LONG")


@dataclass(frozen=True, slots=True)
class AuthorizedReference:
    asset_id: str
    asset_version: str
    role: ReferenceRole
    source: ReferenceSource
    durable_ref: str
    rights: Rights
    commercial_use_allowed: bool
    checksum_sha256: str
    mime_type: str
    approval_state: str | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.durable_ref, "AUTHORIZED_REFERENCE_DURABLE_REF_REQUIRED")
        if "://" in self.durable_ref:
            raise ValueError("AUTHORIZED_REFERENCE_SIGNED_URL_FORBIDDEN")
        _require_sha256(self.checksum_sha256, "AUTHORIZED_REFERENCE_CHECKSUM_INVALID")


@dataclass(frozen=True, slots=True)
class IdentityRequirement:
    identity_id: str
    reference_set_version: str
    severity: ConstraintSeverity
    scenario: str

    def __post_init__(self) -> None:
        _require_nonblank(self.identity_id, "IDENTITY_REQUIREMENT_ID_REQUIRED")
        _require_nonblank(self.reference_set_version, "IDENTITY_REQUIREMENT_VERSION_REQUIRED")
        _require_nonblank(self.scenario, "IDENTITY_REQUIREMENT_SCENARIO_REQUIRED")


@dataclass(frozen=True, slots=True)
class GenerationConstraint:
    constraint_id: str
    constraint_type: str
    severity: ConstraintSeverity
    snapshot_hash: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_nonblank(self.constraint_id, "GENERATION_CONSTRAINT_ID_REQUIRED")
        _require_nonblank(self.constraint_type, "GENERATION_CONSTRAINT_TYPE_REQUIRED")
        _require_sha256(self.snapshot_hash, "GENERATION_CONSTRAINT_SNAPSHOT_INVALID")
        _normalize(self.parameters)


@dataclass(frozen=True, slots=True)
class OutputRequirements:
    format: OutputFormat = "PNG"
    transparent_background: bool = False
    exact_dimensions: bool = True
    minimum_width: int | None = None
    minimum_height: int | None = None

    def __post_init__(self) -> None:
        for value in (self.minimum_width, self.minimum_height):
            if value is not None and value <= 0:
                raise ValueError("IMAGE_OUTPUT_MIN_DIMENSION_INVALID")
        if self.transparent_background and self.format != "PNG":
            raise ValueError("TRANSPARENT_OUTPUT_REQUIRES_PNG")


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

    def __post_init__(self) -> None:
        for value in (self.objective, self.content, self.output_dimensions, self.template_version):
            _require_nonblank(value, "PROMPT_BLOCK_REQUIRED")

    @property
    def prompt_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True, slots=True)
class ImageGenerationSpec:
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
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
    agent_run_id: str | None = None
    recipe_version: str | None = None
    skill_versions: Mapping[str, str] = field(default_factory=dict)
    seed: int | None = None
    user_intent_ref: str | None = None

    def __post_init__(self) -> None:
        for value, code in (
            (self.organization_id, "GENERATION_ORGANIZATION_REQUIRED"),
            (self.project_id, "GENERATION_PROJECT_REQUIRED"),
            (self.task_id, "GENERATION_TASK_REQUIRED"),
            (self.operation_id, "GENERATION_OPERATION_REQUIRED"),
        ):
            _require_uuid(value, code)
        for value in (
            self.purpose,
            self.prompt_compilation_ref,
            self.objective,
            self.content,
            self.aspect_ratio,
        ):
            _require_nonblank(value, "GENERATION_TEXT_FIELD_REQUIRED")
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
        if len(self.references) > 32:
            raise ValueError("GENERATION_REFERENCE_LIMIT")
        if len(self.identity_requirements) > 16:
            raise ValueError("GENERATION_IDENTITY_REQUIREMENT_LIMIT")
        if len(self.constraints) > 128:
            raise ValueError("GENERATION_CONSTRAINT_LIMIT")
        if len(self.code_git_sha) != 40 or any(ch not in "0123456789abcdef" for ch in self.code_git_sha):
            raise ValueError("GENERATION_GIT_SHA_INVALID")
        if self.seed is not None and not 0 <= self.seed <= 2**63 - 1:
            raise ValueError("GENERATION_SEED_INVALID")
        _normalize(self.skill_versions)

    @property
    def semantic_hash(self) -> str:
        # operation_id is intentionally excluded: identical semantics can be compared across
        # operations, while idempotency still keys on (organization_id, operation_id).
        payload = asdict(self)
        payload.pop("operation_id")
        return canonical_hash(payload)

    @property
    def hard_constraint_snapshot_hash(self) -> str:
        snapshots = sorted(
            constraint.snapshot_hash
            for constraint in self.constraints
            if constraint.severity == "HARD"
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
class GatewayGenerationRequest:
    organization_id: str
    project_id: str
    task_id: str
    root_operation_id: str
    variant_operation_id: str
    generation_id: str
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
    agent_run_id: str | None


@dataclass(frozen=True, slots=True)
class ProviderOutputRef:
    ref: str
    mime_type: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.ref, "PROVIDER_OUTPUT_REF_REQUIRED")


@dataclass(frozen=True, slots=True)
class GatewayGenerationResult:
    status: GatewayResultStatus
    provider: str
    model: str
    model_revision: str | None
    provider_request_id: str | None
    outputs: tuple[ProviderOutputRef, ...]
    cost_usd: Decimal | None
    cost_confidence: str
    pricing_snapshot_id: str | None
    routing_reason_codes: tuple[str, ...]
    safety_metadata: Mapping[str, object]
    finish_reason: str | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.cost_usd, float):
            raise ValueError("GENERATION_RESULT_COST_FLOAT_FORBIDDEN")
        if self.cost_usd is not None and (not self.cost_usd.is_finite() or self.cost_usd < 0):
            raise ValueError("GENERATION_RESULT_COST_INVALID")
        _normalize(self.safety_metadata)


@dataclass(frozen=True, slots=True)
class FetchedImage:
    source_ref: str
    content: bytes
    declared_mime_type: str | None


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
    storage_key: str
    mime_type: str
    width: int
    height: int
    size_bytes: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        if not self.storage_key or "://" in self.storage_key:
            raise ValueError("GENERATION_STORAGE_KEY_MUST_BE_DURABLE")
        _require_sha256(self.checksum_sha256, "GENERATION_STORED_CHECKSUM_INVALID")


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
            finding.severity == "HARD" and finding.status in {"FAIL", "UNAVAILABLE"}
            for finding in self.findings
        )


@dataclass(frozen=True, slots=True)
class GenerationProvenanceSnapshot:
    generation_id: str
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    variant_operation_id: str
    variant_index: int
    provider: str
    model: str
    model_revision: str | None
    provider_request_id: str | None
    prompt_hash: str
    prompt_template_version: str
    prompt_compilation_ref: str
    reference_asset_refs: tuple[str, ...]
    seed: int | None
    width: int
    height: int
    quality_profile: QualityProfile
    routing_reason_codes: tuple[str, ...]
    pricing_snapshot_id: str | None
    cost_usd: Decimal | None
    cost_confidence: str
    agent_run_id: str | None
    recipe_version: str | None
    skill_versions: Mapping[str, str]
    code_git_sha: str
    constraint_snapshot_hash: str
    brand_rule_set_version: str | None
    identity_validation_snapshot_id: str | None
    safety_metadata: Mapping[str, object]

    @property
    def snapshot_id(self) -> str:
        return f"image-generation-provenance:{canonical_hash(self)}"


@dataclass(frozen=True, slots=True)
class GenerationCandidate:
    candidate_id: str
    generation_id: str
    variant_index: int
    status: CandidateStatus
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    provider_output_ref: str | None = None
    stored_image: StoredImage | None = None
    artifact_id: str | None = None
    artifact_version_id: str | None = None
    validation: ValidationBundle | None = None
    provenance_snapshot_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationJob:
    generation_id: str
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    semantic_hash: str
    status: GenerationJobStatus
    prompt_hash: str
    variant_decision: VariantDecision
    candidates: tuple[GenerationCandidate, ...]
    created_at: str
    completed_at: str | None = None
    error_code: str | None = None
