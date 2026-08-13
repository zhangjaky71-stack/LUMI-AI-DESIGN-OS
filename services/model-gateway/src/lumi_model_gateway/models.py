from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


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
    VIDEO_EDIT = "video.edit"
    EMBEDDING_TEXT = "embedding.text"
    EMBEDDING_MULTIMODAL = "embedding.multimodal"
    OCR_DOCUMENT = "ocr.document"


class QualityProfile(StrEnum):
    DRAFT = "draft"
    BALANCED = "balanced"
    HIGH = "high"
    MAX = "max"


class LatencyProfile(StrEnum):
    REALTIME = "realtime"
    INTERACTIVE = "interactive"
    BATCH = "batch"


class ProviderLatencyClass(StrEnum):
    FAST = "fast"
    STANDARD = "standard"
    SLOW = "slow"


class ResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PENDING = "pending"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CostConfidence(StrEnum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ModelRequest:
    organization_id: UUID
    operation_id: UUID
    capability: Capability
    inputs: dict[str, Any]
    request_id: UUID = field(default_factory=uuid4)
    project_id: UUID | None = None
    task_id: UUID | None = None
    agent_run_id: UUID | None = None
    generation_id: UUID | None = None
    quality_profile: QualityProfile = QualityProfile.BALANCED
    latency_profile: LatencyProfile = LatencyProfile.INTERACTIVE
    budget_limit_usd: Decimal | None = None
    structured_output_schema: dict[str, Any] | None = None
    reference_assets: tuple[str, ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)
    routing_hints: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.budget_limit_usd, float):
            raise ValueError("MODEL_BUDGET_FLOAT_FORBIDDEN")
        if self.budget_limit_usd is not None and self.budget_limit_usd < 0:
            raise ValueError("MODEL_BUDGET_LIMIT_INVALID")
        if len(self.reference_assets) > 32:
            raise ValueError("MODEL_REFERENCE_ASSET_LIMIT")
        for reference in self.reference_assets:
            if not reference or len(reference) > 1024 or "\x00" in reference:
                raise ValueError("MODEL_REFERENCE_ASSET_INVALID")
        allowed_hints = {
            "preferred_provider",
            "preferred_model",
            "allow_fallback",
        }
        unknown_hints = set(self.routing_hints) - allowed_hints
        if unknown_hints:
            names = ",".join(sorted(unknown_hints))
            raise ValueError(f"MODEL_ROUTING_HINT_UNKNOWN:{names}")
        if self.trace_id is not None and len(self.trace_id) > 128:
            raise ValueError("MODEL_TRACE_ID_INVALID")
        _normalize_json(self.inputs, path="$.inputs", depth=0)
        _normalize_json(self.constraints, path="$.constraints", depth=0)
        if self.structured_output_schema is not None:
            _normalize_json(
                self.structured_output_schema,
                path="$.structured_output_schema",
                depth=0,
            )

    @property
    def semantic_hash(self) -> str:
        payload = {
            "organization_id": str(self.organization_id),
            "operation_id": str(self.operation_id),
            "project_id": str(self.project_id) if self.project_id else None,
            "task_id": str(self.task_id) if self.task_id else None,
            "agent_run_id": str(self.agent_run_id) if self.agent_run_id else None,
            "generation_id": str(self.generation_id) if self.generation_id else None,
            "capability": self.capability.value,
            "quality_profile": self.quality_profile.value,
            "latency_profile": self.latency_profile.value,
            "budget_limit_usd": (
                format(self.budget_limit_usd, "f")
                if self.budget_limit_usd is not None
                else None
            ),
            "inputs": self.inputs,
            "structured_output_schema": self.structured_output_schema,
            "reference_assets": list(self.reference_assets),
            "constraints": self.constraints,
            "routing_hints": self.routing_hints,
        }
        normalized = _normalize_json(payload, path="$", depth=0)
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderModel:
    provider: str
    model: str
    capabilities: frozenset[Capability]
    quality_score: int
    latency_class: ProviderLatencyClass
    regions: frozenset[str] = frozenset()
    supports_streaming: bool = False
    supports_async: bool = False

    def __post_init__(self) -> None:
        if not self.provider or len(self.provider) > 100:
            raise ValueError("PROVIDER_NAME_INVALID")
        if not self.model or len(self.model) > 255:
            raise ValueError("PROVIDER_MODEL_INVALID")
        if not 0 <= self.quality_score <= 100:
            raise ValueError("PROVIDER_QUALITY_SCORE_INVALID")
        if not self.capabilities:
            raise ValueError("PROVIDER_CAPABILITIES_REQUIRED")

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True, slots=True)
class CostEstimate:
    amount_usd: Decimal | None
    confidence: CostConfidence
    price_snapshot_id: str | None = None
    detail: dict[str, Decimal | int | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.amount_usd, float):
            raise ValueError("MODEL_COST_FLOAT_FORBIDDEN")
        if self.amount_usd is not None:
            if not self.amount_usd.is_finite() or self.amount_usd < 0:
                raise ValueError("MODEL_COST_AMOUNT_INVALID")
        if self.price_snapshot_id is not None and len(self.price_snapshot_id) > 128:
            raise ValueError("MODEL_PRICE_SNAPSHOT_INVALID")
        for key, value in self.detail.items():
            if not key or len(key) > 128:
                raise ValueError("MODEL_COST_DETAIL_KEY_INVALID")
            if isinstance(value, float):
                raise ValueError("MODEL_COST_DETAIL_FLOAT_FORBIDDEN")
            if isinstance(value, Decimal) and not value.is_finite():
                raise ValueError("MODEL_COST_DETAIL_NON_FINITE")


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    image_input_tokens: int | None = None
    image_output_tokens: int | None = None
    seconds: Decimal | None = None
    units: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (
            self.input_tokens,
            self.output_tokens,
            self.total_tokens,
            self.cached_input_tokens,
            self.image_input_tokens,
            self.image_output_tokens,
        ):
            if value is not None and value < 0:
                raise ValueError("MODEL_USAGE_NEGATIVE")
        if self.seconds is not None and (not self.seconds.is_finite() or self.seconds < 0):
            raise ValueError("MODEL_USAGE_SECONDS_INVALID")
        for key, value in self.units.items():
            if not key or len(key) > 100:
                raise ValueError("MODEL_USAGE_UNIT_KEY_INVALID")
            if not value.is_finite() or value < 0:
                raise ValueError("MODEL_USAGE_UNIT_VALUE_INVALID")


@dataclass(frozen=True, slots=True)
class Timing:
    total_ms: int
    ttft_ms: int | None = None
    queue_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ModelOutput:
    kind: str
    value: Any
    mime_type: str | None = None

    def __post_init__(self) -> None:
        if not self.kind or len(self.kind) > 64:
            raise ValueError("MODEL_OUTPUT_KIND_INVALID")
        if isinstance(self.value, (bytes, bytearray, memoryview)):
            raise ValueError("MODEL_OUTPUT_BINARY_FORBIDDEN")
        _normalize_json(self.value, path="$.output", depth=0)


@dataclass(frozen=True, slots=True)
class ModelResult:
    status: ResultStatus
    provider: str
    model: str
    provider_request_id: str | None
    outputs: tuple[ModelOutput, ...]
    usage: Usage
    timing: Timing
    cost: CostEstimate
    safety_metadata: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None
    raw_response_ref: str | None = None


@dataclass(frozen=True, slots=True)
class StreamChunk:
    request_id: UUID
    provider: str
    model: str
    sequence: int
    kind: str
    delta: str | None = None
    usage: Usage | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    provider: str
    model: str
    estimate: CostEstimate
    score: int
    reason_codes: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    request_id: UUID
    candidates: tuple[RouteCandidate, ...]
    rejected: dict[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        if not self.candidates:
            raise ValueError("MODEL_ROUTE_EMPTY")


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    request_id: UUID
    organization_id: UUID
    operation_id: UUID
    capability: Capability
    provider: str
    model: str
    routing_reason_codes: tuple[str, ...]
    attempt: int
    fallback_index: int
    retry_count: int
    latency_ms: int
    usage: Usage | None
    cost: CostEstimate | None
    error_category: str | None
    semantic_hash: str
    trace_id: str | None
    project_id: UUID | None = None
    task_id: UUID | None = None
    agent_run_id: UUID | None = None
    generation_id: UUID | None = None
    provider_request_id: str | None = None


def quality_threshold(profile: QualityProfile) -> int:
    return {
        QualityProfile.DRAFT: 35,
        QualityProfile.BALANCED: 55,
        QualityProfile.HIGH: 75,
        QualityProfile.MAX: 90,
    }[profile]


def latency_allowed(
    profile: LatencyProfile,
    latency_class: ProviderLatencyClass,
) -> bool:
    if profile == LatencyProfile.REALTIME:
        return latency_class == ProviderLatencyClass.FAST
    if profile == LatencyProfile.INTERACTIVE:
        return latency_class in {
            ProviderLatencyClass.FAST,
            ProviderLatencyClass.STANDARD,
        }
    return True


def _normalize_json(value: Any, *, path: str, depth: int) -> Any:
    if depth > 24:
        raise ValueError("MODEL_JSON_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"MODEL_NON_FINITE_NUMBER:{path}")
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"MODEL_JSON_NON_STRING_KEY:{path}")
            normalized[key] = _normalize_json(
                child,
                path=f"{path}.{key}",
                depth=depth + 1,
            )
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json(child, path=f"{path}[{index}]", depth=depth + 1)
            for index, child in enumerate(value)
        ]
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"MODEL_BINARY_VALUE_FORBIDDEN:{path}")
    raise ValueError(f"MODEL_JSON_VALUE_UNSUPPORTED:{path}:{type(value).__name__}")
