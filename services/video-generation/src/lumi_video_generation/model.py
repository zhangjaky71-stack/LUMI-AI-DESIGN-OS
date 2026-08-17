from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class VideoMode(StrEnum):
    TEXT_TO_VIDEO = "TEXT_TO_VIDEO"
    IMAGE_TO_VIDEO = "IMAGE_TO_VIDEO"
    KEYFRAME_TO_VIDEO = "KEYFRAME_TO_VIDEO"
    PRODUCT_MOTION = "PRODUCT_MOTION"
    LOOP = "LOOP"


class VideoJobStatus(StrEnum):
    PLANNED = "PLANNED"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    VALIDATING = "VALIDATING"
    COMPOSING = "COMPOSING"
    COMPLETED = "COMPLETED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ShotStatus(StrEnum):
    PLANNED = "PLANNED"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ValidationDecision(StrEnum):
    PASS = "PASS"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class SourceImageRef:
    asset_id: str
    asset_version: str
    durable_ref: str
    checksum_sha256: str
    rights_snapshot_id: str

    def __post_init__(self) -> None:
        if len(self.checksum_sha256) != 64:
            raise ValueError("source checksum must be sha256")
        try:
            int(self.checksum_sha256, 16)
        except ValueError as exc:
            raise ValueError("source checksum must be lowercase hex sha256") from exc
        if self.checksum_sha256.lower() != self.checksum_sha256:
            raise ValueError("source checksum must be lowercase hex sha256")
        if not self.durable_ref:
            raise ValueError("source durable_ref is required")


@dataclass(frozen=True, slots=True)
class ShotSpec:
    shot_id: str
    duration_seconds: Decimal
    prompt: str
    source_ref: SourceImageRef | None = None
    camera_motion: str | None = None
    subject_action: str | None = None
    transition: str = "CUT"
    identity_refs: tuple[str, ...] = ()
    required_features: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.shot_id or not self.prompt.strip():
            raise ValueError("shot_id and prompt are required")
        if self.duration_seconds <= 0 or self.duration_seconds > Decimal("30"):
            raise ValueError("shot duration must be >0 and <=30 seconds")
        if self.transition not in {"CUT", "FADE"}:
            raise ValueError("unsupported transition")


@dataclass(frozen=True, slots=True)
class VideoTaskSpec:
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    mode: VideoMode
    width: int
    height: int
    fps: int
    shots: tuple[ShotSpec, ...]
    budget_limit_usd: Decimal | None = None
    negative_prompt: str | None = None
    seed: int | None = None
    agent_run_id: str | None = None
    brand_rule_snapshot_id: str | None = None
    agent_id: str | None = None
    recipe_id: str | None = None
    skill_refs: tuple[str, ...] = ()
    git_commit: str | None = None
    user_use_declaration: str | None = None

    def __post_init__(self) -> None:
        if not self.organization_id or not self.project_id or not self.task_id:
            raise ValueError("tenant/project/task identifiers are required")
        if not self.operation_id:
            raise ValueError("operation_id is required")
        if self.width <= 0 or self.height <= 0 or self.fps <= 0:
            raise ValueError("video dimensions and fps must be positive")
        if self.width > 8192 or self.height > 8192 or self.fps > 120:
            raise ValueError("video dimensions or fps exceed safety bounds")
        if not self.shots:
            raise ValueError("at least one shot is required")
        if len({shot.shot_id for shot in self.shots}) != len(self.shots):
            raise ValueError("shot_id must be unique")
        if self.budget_limit_usd is not None and self.budget_limit_usd < 0:
            raise ValueError("budget limit cannot be negative")
        if self.git_commit is not None:
            if len(self.git_commit) != 40:
                raise ValueError("git_commit must be a 40-character git sha")
            try:
                int(self.git_commit, 16)
            except ValueError as exc:
                raise ValueError("git_commit must be lowercase hexadecimal") from exc
            if self.git_commit.lower() != self.git_commit:
                raise ValueError("git_commit must be lowercase hexadecimal")

    @property
    def total_duration_seconds(self) -> Decimal:
        return sum((shot.duration_seconds for shot in self.shots), Decimal("0"))

    def semantic_hash(self) -> str:
        payload = json.dumps(
            _jsonable(asdict(self)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CompiledShot:
    index: int
    shot: ShotSpec
    paid_operation_id: str
    continuity_refs: tuple[str, ...] = ()
    retry_ordinal: int = 0


@dataclass(frozen=True, slots=True)
class GatewayEstimate:
    amount_usd: Decimal
    provider: str
    model: str
    pricing_snapshot_id: str | None
    routing_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GatewayVideoResult:
    status: str
    provider: str
    model: str
    provider_request_id: str | None = None
    output_ref: str | None = None
    output_mime_type: str | None = None
    cost_usd: Decimal | None = None
    pricing_snapshot_id: str | None = None
    routing_reason_codes: tuple[str, ...] = ()
    safety_metadata: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderJobRecord:
    shot_id: str
    operation_id: str
    capability: str
    queued_at_epoch: float
    result: GatewayVideoResult


@dataclass(frozen=True, slots=True)
class VideoProbeResult:
    mime_type: str
    width: int
    height: int
    duration_seconds: Decimal
    decodable_frames: int
    black_frame_ratio: Decimal = Decimal("0")
    has_audio: bool = False


@dataclass(frozen=True, slots=True)
class ShotValidationReport:
    decision: ValidationDecision
    reason_codes: tuple[str, ...]
    identity_checked: bool
    brand_checked: bool


@dataclass(frozen=True, slots=True)
class StoredVideoClip:
    shot_id: str
    durable_ref: str
    checksum_sha256: str
    probe: VideoProbeResult
    provider: str
    model: str
    provider_request_id: str


@dataclass(frozen=True, slots=True)
class ShotRuntime:
    compiled: CompiledShot
    status: ShotStatus = ShotStatus.PLANNED
    pending: ProviderJobRecord | None = None
    clip: StoredVideoClip | None = None
    validation: ShotValidationReport | None = None
    actual_cost_usd: Decimal = Decimal("0")
    artifact_version_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class TimelineClip:
    shot_id: str
    durable_ref: str
    start_seconds: Decimal
    duration_seconds: Decimal
    transition: str


@dataclass(frozen=True, slots=True)
class VideoTimeline:
    clips: tuple[TimelineClip, ...]
    width: int
    height: int
    fps: int
    audio_ref: str | None = None
    subtitle_ref: str | None = None


@dataclass(frozen=True, slots=True)
class RenderedVideo:
    durable_ref: str
    checksum_sha256: str
    probe: VideoProbeResult
    renderer_version: str


@dataclass(frozen=True, slots=True)
class ShotProvenance:
    shot_id: str
    operation_id: str
    retry_ordinal: int
    provider: str
    model: str
    provider_request_id: str
    source_asset_ids: tuple[str, ...]
    identity_refs: tuple[str, ...]
    rights_snapshot_ids: tuple[str, ...]
    cost_usd: Decimal
    artifact_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class FinalVideoProvenance:
    task_semantic_hash: str
    source_shots: tuple[ShotProvenance, ...]
    renderer_version: str
    brand_rule_snapshot_id: str | None
    agent_run_id: str | None
    agent_id: str | None
    recipe_id: str | None
    skill_refs: tuple[str, ...]
    git_commit: str | None


@dataclass(frozen=True, slots=True)
class VideoJob:
    job_id: str
    spec: VideoTaskSpec
    status: VideoJobStatus
    shots: tuple[ShotRuntime, ...]
    final_video: RenderedVideo | None = None
    provenance: FinalVideoProvenance | None = None
    final_artifact_version_id: str | None = None
    error_code: str | None = None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
