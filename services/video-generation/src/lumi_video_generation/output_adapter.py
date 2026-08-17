from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from .model import (
    CompiledShot,
    DurableVideoObject,
    GatewayVideoResult,
    StoredVideoClip,
    VideoProbeResult,
    VideoTaskSpec,
)


class ProviderOutputFetchPort(Protocol):
    async def fetch_to_staging(
        self,
        *,
        organization_id: str,
        provider: str,
        provider_output_ref: str,
    ) -> tuple[bytes, str]: ...


class VideoProbePort(Protocol):
    async def probe(
        self,
        *,
        payload: bytes,
        mime_type: str,
    ) -> VideoProbeResult: ...


class DurableVideoStorePort(Protocol):
    async def put_verified(
        self,
        *,
        organization_id: str,
        project_id: str,
        payload: bytes,
        mime_type: str,
        checksum_sha256: str,
    ) -> DurableVideoObject: ...


@dataclass(slots=True)
class VerifiedVideoOutputAdapter:
    fetcher: ProviderOutputFetchPort
    probe_port: VideoProbePort
    store: DurableVideoStorePort
    max_bytes: int = 2_000_000_000

    async def materialize_and_validate(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        result: GatewayVideoResult,
    ) -> StoredVideoClip:
        if result.status != "COMPLETED":
            raise ValueError("VIDEO_OUTPUT_REQUIRES_COMPLETED_PROVIDER_RESULT")
        if not result.output_ref or not result.provider_request_id:
            raise ValueError("VIDEO_PROVIDER_OUTPUT_REF_REQUIRED")
        payload, mime_type = await self.fetcher.fetch_to_staging(
            organization_id=spec.organization_id,
            provider=result.provider,
            provider_output_ref=result.output_ref,
        )
        if not payload or len(payload) > self.max_bytes:
            raise ValueError("VIDEO_PROVIDER_OUTPUT_SIZE_INVALID")
        if mime_type not in {"video/mp4", "video/webm"}:
            raise ValueError("VIDEO_PROVIDER_OUTPUT_MIME_INVALID")
        probe = await self.probe_port.probe(
            payload=payload,
            mime_type=mime_type,
        )
        if probe.mime_type != mime_type:
            raise ValueError("VIDEO_PROVIDER_OUTPUT_PROBE_MIME_MISMATCH")
        checksum = hashlib.sha256(payload).hexdigest()
        stored = await self.store.put_verified(
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            payload=payload,
            mime_type=mime_type,
            checksum_sha256=checksum,
        )
        if stored.size_bytes != len(payload):
            raise ValueError("VIDEO_DURABLE_STORAGE_SIZE_MISMATCH")
        return StoredVideoClip(
            shot_id=shot.shot.shot_id,
            object=stored,
            checksum_sha256=checksum,
            probe=probe,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
        )
