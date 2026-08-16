from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID


class Capability(StrEnum):
    LLM_REASONING = "llm.reasoning"
    LLM_STRUCTURED_OUTPUT = "llm.structured_output"
    LLM_VISION = "llm.vision"
    IMAGE_GENERATE = "image.generate"
    IMAGE_EDIT = "image.edit"
    IMAGE_MASK_EDIT = "image.mask_edit"
    IMAGE_REFERENCE_CONSISTENCY = "image.reference_consistency"
    IMAGE_TRANSPARENT_BACKGROUND = "image.transparent_background"
    VIDEO_TEXT_TO_VIDEO = "video.text_to_video"
    VIDEO_IMAGE_TO_VIDEO = "video.image_to_video"
    EMBEDDING_TEXT = "embedding.text"
    EMBEDDING_MULTIMODAL = "embedding.multimodal"
    OCR_DOCUMENT = "ocr.document"


class InputKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"


class QualityProfile(StrEnum):
    DRAFT = "draft"
    BALANCED = "balanced"
    HIGH = "high"
    MAX = "max"


class LatencyProfile(StrEnum):
    INTERACTIVE = "interactive"
    STANDARD = "standard"
    BATCH = "batch"


class ResultStatus(StrEnum):
    COMPLETED = "completed"
    PENDING = "pending"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CostConfidence(StrEnum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class StreamEventType(StrEnum):
    STARTED = "started"
    TEXT_DELTA = "text_delta"
    USAGE = "usage"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ModelInput:
    kind: InputKind
    role: str = "user"
    text: str | None = None
    uri: str | None = None
    media_type: str | None = None

    def __post_init__(self) -> None:
        if self.kind is InputKind.TEXT and not self.text:
            raise ValueError("text input requires text")
        if self.kind in {InputKind.IMAGE, InputKind.DOCUMENT} and not self.uri:
            raise ValueError(f"{self.kind.value} input requires uri")
        if self.role not in {"user", "assistant", "system", "developer"}:
            raise ValueError("unsupported input role")


@dataclass(frozen=True, slots=True)
class RoutingHints:
    preferred_providers: tuple[str, ...] = ()
    preferred_models: tuple[str, ...] = ()
    excluded_providers: tuple[str, ...] = ()
    required_region: str | None = None
    allow_fallback: bool = True
    allow_unknown_cost: bool = False


@dataclass(frozen=True, slots=True)
class ModelRequest:
    request_id: UUID
    organization_id: UUID
    operation_id: UUID
    capability: Capability
    inputs: tuple[ModelInput, ...]
    quality_profile: QualityProfile = QualityProfile.BALANCED
    latency_profile: LatencyProfile = LatencyProfile.STANDARD
    budget_limit: Decimal | None = None
    project_id: UUID | None = None
    task_id: UUID | None = None
    structured_output_schema: dict[str, Any] | None = None
    reference_assets: tuple[str, ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)
    routing_hints: RoutingHints = field(default_factory=RoutingHints)
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not self.inputs:
            raise ValueError("model request requires at least one input")
        if self.budget_limit is not None and self.budget_limit < 0:
            raise ValueError("budget_limit cannot be negative")
        if self.capability is Capability.LLM_STRUCTURED_OUTPUT and not self.structured_output_schema:
            raise ValueError("structured output capability requires a schema")

    def semantic_hash(self) -> str:
        payload = {
            "organization_id": self.organization_id,
            "operation_id": self.operation_id,
            "capability": self.capability,
            "inputs": self.inputs,
            "quality_profile": self.quality_profile,
            "latency_profile": self.latency_profile,
            "budget_limit": self.budget_limit,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "structured_output_schema": self.structured_output_schema,
            "reference_assets": self.reference_assets,
            "constraints": self.constraints,
            "routing_hints": self.routing_hints,
        }
        encoded = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderModel:
    provider: str
    model: str
    capabilities: frozenset[Capability]
    quality_score: int = 50
    latency_score: int = 50
    regions: frozenset[str] = frozenset({"global"})
    paid: bool = True
    input_usd_per_million: Decimal | None = None
    output_usd_per_million: Decimal | None = None
    fixed_request_usd: Decimal | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.quality_score <= 100 or not 0 <= self.latency_score <= 100:
            raise ValueError("quality_score and latency_score must be 0..100")


@dataclass(frozen=True, slots=True)
class CostEstimate:
    amount_usd: Decimal | None
    confidence: CostConfidence
    pricing_snapshot_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    images: int = 0
    video_seconds: Decimal = Decimal("0")
    requests: int = 1


@dataclass(frozen=True, slots=True)
class ModelTiming:
    total_ms: int
    ttft_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ModelOutput:
    kind: str
    text: str | None = None
    json_value: Any | None = None
    asset_ref: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedResult:
    status: ResultStatus
    provider: str
    model: str
    outputs: tuple[ModelOutput, ...] = ()
    provider_request_id: str | None = None
    usage: ModelUsage = field(default_factory=ModelUsage)
    timing: ModelTiming | None = None
    safety_metadata: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None
    raw_response_ref: str | None = None
    cost: CostEstimate = field(default_factory=lambda: CostEstimate(None, CostConfidence.UNKNOWN))


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    healthy: bool = True
    score: int = 100
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    model: ProviderModel
    estimate: CostEstimate
    health: HealthSnapshot
    score: int
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteDecision:
    request_id: UUID
    candidates: tuple[RouteCandidate, ...]
    rejected_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelStreamChunk:
    event: StreamEventType
    provider: str
    model: str
    text_delta: str | None = None
    usage: ModelUsage | None = None
    provider_request_id: str | None = None
    finish_reason: str | None = None


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value
