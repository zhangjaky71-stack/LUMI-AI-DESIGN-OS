from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Literal, Mapping

VideoMode = Literal["TEXT_TO_VIDEO", "IMAGE_TO_VIDEO", "STORYBOARD_MULTI_SHOT"]
JobStatus = Literal[
    "SUBMITTING",
    "WAITING_EXTERNAL",
    "VALIDATING",
    "COMPOSING",
    "COMPLETED",
    "PARTIAL",
    "FAILED",
    "CANCELLED",
]
ShotStatus = Literal["QUEUED", "WAITING_EXTERNAL", "READY", "FAILED", "DROPPED", "CANCELLED"]
ValidationDecision = Literal["PASS", "REPAIR", "REJECT"]
ContinuityKind = Literal["FIRST_FRAME", "PREVIOUS_TAIL", "EXPLICIT_REFERENCE"]
TransitionKind = Literal["CUT", "CROSSFADE"]


def _decimal_text(value: Decimal) -> str:
    if isinstance(value, float):
        raise ValueError("VIDEO_FLOAT_FORBIDDEN")
    if not value.is_finite():
        raise ValueError("VIDEO_DECIMAL_NON_FINITE")
    return format(value, "f")


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label}_INVALID")


@dataclass(frozen=True, slots=True)
class SourceImageRef:
    asset_id: str
    asset_version: str
    durable_ref: str
    checksum_sha256: str
    commercial_use_allowed: bool
    artifact_version_id: str | None = None

    def __post_init__(self) -> None:
        _require_sha256(self.checksum_sha256, "VIDEO_SOURCE_CHECKSUM")
        if not self.durable_ref or "://" in self.durable_ref:
            raise ValueError("VIDEO_SOURCE_DURABLE_REF_INVALID")


@dataclass(frozen=True, slots=True)
class IdentityRequirement:
    identity_id: str
    reference_set_version: str
    severity: Literal["HARD", "SOFT", "ADVISORY"] = "HARD"


@dataclass(frozen=True, slots=True)
class ContinuityRef:
    kind: ContinuityKind
    durable_ref: str | None = None
    source_shot_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "EXPLICIT_REFERENCE" and not self.durable_ref:
            raise ValueError("VIDEO_CONTINUITY_EXPLICIT_REF_REQUIRED")
        if self.kind == "PREVIOUS_TAIL" and not self.source_shot_id:
            raise ValueError("VIDEO_CONTINUITY_SOURCE_SHOT_REQUIRED")
        if self.durable_ref is not None and "://" in self.durable_ref:
            raise ValueError("VIDEO_CONTINUITY_REF_MUST_BE_DURABLE")


@dataclass(frozen=True, slots=True)
class ShotSpec:
    shot_id: str
    duration_seconds: Decimal
    prompt: str
    camera_motion: str | None = None
    subject_action: str | None = None
    source_ref: SourceImageRef | None = None
    continuity_refs: tuple[ContinuityRef, ...] = ()
    transition_to_next: TransitionKind = "CUT"
    optional: bool = False

    def __post_init__(self) -> None:
        if not self.shot_id or len(self.shot_id) > 128:
            raise ValueError("VIDEO_SHOT_ID_INVALID")
        if isinstance(self.duration_seconds, float):
            raise ValueError("VIDEO_SHOT_DURATION_FLOAT_FORBIDDEN")
        if not self.duration_seconds.is_finite() or self.duration_seconds <= 0:
            raise ValueError("VIDEO_SHOT_DURATION_INVALID")
        if not self.prompt.strip():
            raise ValueError("VIDEO_SHOT_PROMPT_REQUIRED")


@dataclass(frozen=True, slots=True)
class AudioTrackSpec:
    durable_ref: str
    offset_seconds: Decimal = Decimal("0")
    gain_db: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.durable_ref or "://" in self.durable_ref:
            raise ValueError("VIDEO_AUDIO_REF_INVALID")
        for value in (self.offset_seconds, self.gain_db):
            if isinstance(value, float) or not value.is_finite():
                raise ValueError("VIDEO_AUDIO_DECIMAL_INVALID")


@dataclass(frozen=True, slots=True)
class VideoTaskSpec:
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    mode: VideoMode
    prompt: str
    duration_seconds: Decimal
    aspect_ratio: str
    width: int
    height: int
    fps: int
    budget_limit_usd: Decimal
    code_git_sha: str
    source_images: tuple[SourceImageRef, ...] = ()
    shots: tuple[ShotSpec, ...] = ()
    audio_tracks: tuple[AudioTrackSpec, ...] = ()
    brand_rule_set_version: str | None = None
    identity_requirements: tuple[IdentityRequirement, ...] = ()
    agent_run_id: str | None = None
    recipe_version: str | None = None
    allow_optional_shot_drop: bool = False
    negative_prompt: str | None = None
    seed: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if isinstance(self.duration_seconds, float) or not self.duration_seconds.is_finite() or self.duration_seconds <= 0:
            raise ValueError("VIDEO_DURATION_INVALID")
        if isinstance(self.budget_limit_usd, float) or not self.budget_limit_usd.is_finite() or self.budget_limit_usd < 0:
            raise ValueError("VIDEO_BUDGET_INVALID")
        if self.width <= 0 or self.height <= 0 or self.fps <= 0:
            raise ValueError("VIDEO_OUTPUT_GEOMETRY_INVALID")
        if self.mode == "IMAGE_TO_VIDEO" and not self.source_images:
            raise ValueError("VIDEO_IMAGE_TO_VIDEO_SOURCE_REQUIRED")
        if self.mode == "STORYBOARD_MULTI_SHOT" and not self.shots:
            raise ValueError("VIDEO_STORYBOARD_SHOTS_REQUIRED")
        if self.mode != "STORYBOARD_MULTI_SHOT" and len(self.shots) > 1:
            raise ValueError("VIDEO_SINGLE_MODE_MULTIPLE_SHOTS_FORBIDDEN")
        if any(not source.commercial_use_allowed for source in self.source_images):
            raise ValueError("VIDEO_SOURCE_COMMERCIAL_RIGHTS_NOT_ALLOWED")
        if len(self.code_git_sha) != 40 or any(char not in "0123456789abcdef" for char in self.code_git_sha):
            raise ValueError("VIDEO_CODE_GIT_SHA_INVALID")

    @property
    def semantic_hash(self) -> str:
        return _canonical_hash({
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "mode": self.mode,
            "prompt": self.prompt,
            "duration_seconds": _decimal_text(self.duration_seconds),
            "aspect_ratio": self.aspect_ratio,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "budget_limit_usd": _decimal_text(self.budget_limit_usd),
            "source_images": [(item.asset_id, item.asset_version, item.checksum_sha256) for item in self.source_images],
            "shots": [
                {
                    "id": shot.shot_id,
                    "duration": _decimal_text(shot.duration_seconds),
                    "prompt": shot.prompt,
                    "camera": shot.camera_motion,
                    "action": shot.subject_action,
                    "source": (shot.source_ref.asset_id, shot.source_ref.asset_version) if shot.source_ref else None,
                    "continuity": [(item.kind, item.durable_ref, item.source_shot_id) for item in shot.continuity_refs],
                    "transition": shot.transition_to_next,
                    "optional": shot.optional,
                }
                for shot in self.shots
            ],
            "audio": [(item.durable_ref, _decimal_text(item.offset_seconds), _decimal_text(item.gain_db)) for item in self.audio_tracks],
            "brand": self.brand_rule_set_version,
            "identity": [(item.identity_id, item.reference_set_version, item.severity) for item in self.identity_requirements],
            "allow_optional_drop": self.allow_optional_shot_drop,
            "negative_prompt": self.negative_prompt,
            "seed": self.seed,
        })


@dataclass(frozen=True, slots=True)
class CompiledShot:
    shot: ShotSpec
    paid_operation_id: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class CompiledStoryboard:
    shots: tuple[CompiledShot, ...]
    total_duration_seconds: Decimal
    storyboard_hash: str


@dataclass(frozen=True, slots=True)
class GatewayEstimate:
    amount_usd: Decimal
    provider: str
    model: str
    pricing_snapshot_id: str | None
    routing_reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GatewayVideoResult:
    status: Literal["PENDING", "SUCCEEDED", "FAILED", "CANCELLED"]
    provider: str
    model: str
    provider_request_id: str | None
    output_ref: str | None
    output_mime_type: str | None
    cost_usd: Decimal | None
    cost_confidence: str
    pricing_snapshot_id: str | None
    routing_reason_codes: tuple[str, ...]
    safety_metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderJobRecord:
    organization_id: str
    video_job_id: str
    shot_id: str
    paid_operation_id: str
    request_hash: str
    result: GatewayVideoResult


@dataclass(frozen=True, slots=True)
class VideoProbeResult:
    decode_ok: bool
    mime_type: str
    container: str
    video_codec: str
    width: int
    height: int
    fps: Decimal
    duration_seconds: Decimal
    keyframe_refs: tuple[str, ...]
    poster_frame_ref: str | None
    tail_frame_ref: str | None
    has_audio: bool = False


@dataclass(frozen=True, slots=True)
class StoredVideoClip:
    storage_key: str
    checksum_sha256: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    duration_ms: int
    durable_asset_ref: str
    poster_frame_ref: str | None
    tail_frame_ref: str | None
    keyframe_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.storage_key or "://" in self.storage_key:
            raise ValueError("VIDEO_STORAGE_KEY_INVALID")
        if not self.durable_asset_ref or "://" in self.durable_asset_ref:
            raise ValueError("VIDEO_DURABLE_ASSET_REF_INVALID")
        _require_sha256(self.checksum_sha256, "VIDEO_CLIP_CHECKSUM")
        if self.size_bytes <= 0 or self.width <= 0 or self.height <= 0 or self.duration_ms <= 0:
            raise ValueError("VIDEO_CLIP_METADATA_INVALID")
        if self.mime_type != "video/mp4":
            raise ValueError("VIDEO_CLIP_MIME_UNSUPPORTED")


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    validator: str
    status: Literal["PASS", "FAIL", "UNAVAILABLE"]
    severity: Literal["HARD", "SOFT", "ADVISORY"]
    reason_code: str
    evidence_ref: str | None = None
    expected: object | None = None
    actual: object | None = None


@dataclass(frozen=True, slots=True)
class ShotValidationReport:
    decision: ValidationDecision
    findings: tuple[ValidationFinding, ...]
    identity_validation_snapshot_id: str | None = None
    brand_validation_snapshot_id: str | None = None


@dataclass(frozen=True, slots=True)
class ShotRuntime:
    shot_id: str
    ordinal: int
    paid_operation_id: str
    status: ShotStatus = "QUEUED"
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    clip_artifact_version_id: str | None = None
    clip: StoredVideoClip | None = None
    validation: ShotValidationReport | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class VideoJob:
    video_job_id: str
    organization_id: str
    operation_id: str
    semantic_hash: str
    storyboard_hash: str
    status: JobStatus
    shots: tuple[ShotRuntime, ...]
    estimated_cost_usd: Decimal = Decimal("0")
    actual_cost_usd: Decimal = Decimal("0")
    final_artifact_version_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class TimelineClip:
    shot_id: str
    artifact_version_id: str
    durable_ref: str
    duration_seconds: Decimal


@dataclass(frozen=True, slots=True)
class TimelineOverlay:
    durable_ref: str
    start_seconds: Decimal
    end_seconds: Decimal
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class TimelineAudioTrack:
    durable_ref: str
    offset_seconds: Decimal
    gain_db: Decimal


@dataclass(frozen=True, slots=True)
class TimelineTransition:
    from_shot_id: str
    to_shot_id: str
    kind: TransitionKind
    duration_seconds: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class VideoOutputSpec:
    width: int
    height: int
    fps: int
    container: Literal["MP4"] = "MP4"
    video_codec: Literal["H264"] = "H264"
    audio_codec: Literal["AAC"] = "AAC"


@dataclass(frozen=True, slots=True)
class VideoTimeline:
    clips: tuple[TimelineClip, ...]
    overlays: tuple[TimelineOverlay, ...]
    audio_tracks: tuple[TimelineAudioTrack, ...]
    transitions: tuple[TimelineTransition, ...]
    output_spec: VideoOutputSpec


@dataclass(frozen=True, slots=True)
class RenderedVideo:
    video: StoredVideoClip
    thumbnail_storage_key: str | None = None
    thumbnail_checksum_sha256: str | None = None
    subtitle_storage_key: str | None = None
    subtitle_checksum_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ShotProvenance:
    video_job_id: str
    organization_id: str
    shot_id: str
    paid_operation_id: str
    storyboard_hash: str
    prompt_hash: str
    source_refs: tuple[str, ...]
    continuity_refs: tuple[str, ...]
    provider: str
    model: str
    provider_request_id: str | None
    routing_reason_codes: tuple[str, ...]
    pricing_snapshot_id: str | None
    cost_usd: Decimal | None
    cost_confidence: str
    brand_rule_set_version: str | None
    identity_validation_snapshot_id: str | None
    code_git_sha: str

    @property
    def snapshot_id(self) -> str:
        return "video-shot-provenance:" + _canonical_hash(self)


@dataclass(frozen=True, slots=True)
class FinalVideoProvenance:
    video_job_id: str
    organization_id: str
    storyboard_hash: str
    clip_artifact_version_ids: tuple[str, ...]
    timeline_hash: str
    code_git_sha: str
    brand_rule_set_version: str | None

    @property
    def snapshot_id(self) -> str:
        return "video-final-provenance:" + _canonical_hash(self)


def timeline_hash(timeline: VideoTimeline) -> str:
    return _canonical_hash(timeline)
