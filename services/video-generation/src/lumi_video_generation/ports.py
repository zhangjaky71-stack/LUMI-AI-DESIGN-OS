from __future__ import annotations

from typing import Protocol

from .model import (
    CompiledShot,
    GatewayEstimate,
    GatewayVideoResult,
    ProviderJobRecord,
    RenderedVideo,
    ShotValidationReport,
    StoredVideoClip,
    VideoJob,
    VideoTaskSpec,
    VideoTimeline,
)


class VideoGatewayPort(Protocol):
    async def estimate(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> GatewayEstimate: ...

    async def submit(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> GatewayVideoResult: ...

    async def poll(self, *, pending: ProviderJobRecord) -> GatewayVideoResult: ...

    async def cancel(self, *, pending: ProviderJobRecord) -> bool: ...


class VideoOutputPort(Protocol):
    async def materialize_and_validate(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        result: GatewayVideoResult,
    ) -> StoredVideoClip: ...


class VideoValidationPort(Protocol):
    async def validate(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        clip: StoredVideoClip,
        provider_result: GatewayVideoResult,
    ) -> ShotValidationReport: ...


class VideoRenderPort(Protocol):
    async def render(self, *, timeline: VideoTimeline) -> RenderedVideo: ...


class VideoArtifactPort(Protocol):
    async def append_clip(
        self,
        *,
        job: VideoJob,
        clip: StoredVideoClip,
    ) -> str: ...

    async def append_final(
        self,
        *,
        job: VideoJob,
        video: RenderedVideo,
    ) -> str: ...


class VideoRepositoryPort(Protocol):
    def create(self, job: VideoJob) -> VideoJob: ...

    def get(self, job_id: str) -> VideoJob: ...

    def save(self, job: VideoJob) -> VideoJob: ...

    def claim_webhook(
        self,
        organization_id: str,
        provider: str,
        event_id: str,
    ) -> bool: ...
