from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Protocol

from .model import (
    CompiledShot,
    FinalVideoProvenance,
    GatewayEstimate,
    GatewayVideoResult,
    ProviderJobRecord,
    RenderedVideo,
    ShotProvenance,
    ShotValidationReport,
    StoredVideoClip,
    VideoJob,
    VideoProbeResult,
    VideoTaskSpec,
    VideoTimeline,
)


class VideoRepositoryPort(Protocol):
    def get_by_operation(self, organization_id: str, operation_id: str) -> VideoJob | None: ...
    def get(self, organization_id: str, video_job_id: str) -> VideoJob | None: ...
    def save_spec(self, spec: VideoTaskSpec) -> None: ...
    def get_spec(self, organization_id: str, operation_id: str) -> VideoTaskSpec | None: ...
    def save(self, job: VideoJob) -> None: ...
    def save_provider_job(self, record: ProviderJobRecord) -> None: ...
    def get_provider_job(self, organization_id: str, video_job_id: str, shot_id: str) -> ProviderJobRecord | None: ...
    def delete_provider_job(self, organization_id: str, video_job_id: str, shot_id: str) -> None: ...


class VideoGatewayPort(Protocol):
    async def estimate(self, *, spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> GatewayEstimate: ...
    async def submit(self, *, spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> GatewayVideoResult: ...
    async def poll(self, *, pending: ProviderJobRecord) -> GatewayVideoResult: ...
    async def cancel(self, *, pending: ProviderJobRecord) -> GatewayVideoResult: ...


class VideoOutputPort(Protocol):
    async def materialize_and_probe(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        output_ref: str,
        declared_mime_type: str | None,
    ) -> tuple[StoredVideoClip, VideoProbeResult]: ...


class VideoValidationPort(Protocol):
    async def validate_shot(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        clip: StoredVideoClip,
        probe: VideoProbeResult,
        safety_metadata: Mapping[str, object],
    ) -> ShotValidationReport: ...

    async def validate_final(
        self,
        *,
        spec: VideoTaskSpec,
        timeline: VideoTimeline,
        rendered: RenderedVideo,
    ) -> ShotValidationReport: ...


class VideoArtifactPort(Protocol):
    async def create_clip(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        clip: StoredVideoClip,
        provenance: ShotProvenance,
        validation: ShotValidationReport,
        continuity_parent_version_ids: tuple[str, ...],
    ) -> str: ...

    async def create_final(
        self,
        *,
        spec: VideoTaskSpec,
        rendered: RenderedVideo,
        provenance: FinalVideoProvenance,
        validation: ShotValidationReport,
        clip_artifact_version_ids: tuple[str, ...],
    ) -> str: ...


class MediaSandboxPort(Protocol):
    async def render(self, timeline: VideoTimeline) -> RenderedVideo: ...


class VideoCostPort(Protocol):
    async def record_terminal(
        self,
        *,
        video_job_id: str,
        shot_id: str,
        paid_operation_id: str,
        provider: str,
        model: str,
        provider_request_id: str | None,
        amount_usd: Decimal | None,
        confidence: str,
        pricing_snapshot_id: str | None,
    ) -> bool: ...


class VideoEventPort(Protocol):
    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        video_job_id: str,
        payload: Mapping[str, object],
    ) -> None: ...
