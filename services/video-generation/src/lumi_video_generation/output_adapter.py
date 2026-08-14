from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import CompiledShot, StoredVideoClip, VideoProbeResult, VideoTaskSpec

MAX_PROVIDER_VIDEO_BYTES = 4 * 1024 * 1024 * 1024


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True, slots=True)
class StagedProviderVideo:
    staging_key: str
    checksum_sha256: str
    size_bytes: int
    declared_mime_type: str | None

    def __post_init__(self) -> None:
        if not self.staging_key or "://" in self.staging_key:
            raise ValueError("VIDEO_STAGING_KEY_INVALID")
        if not _valid_sha256(self.checksum_sha256):
            raise ValueError("VIDEO_STAGING_CHECKSUM_INVALID")
        if self.size_bytes <= 0 or self.size_bytes > MAX_PROVIDER_VIDEO_BYTES:
            raise ValueError("VIDEO_STAGING_SIZE_INVALID")


class ProviderVideoFetcher(Protocol):
    async def fetch_to_staging(
        self,
        *,
        source_ref: str,
        declared_mime_type: str | None,
        max_bytes: int,
    ) -> StagedProviderVideo: ...


class VideoProbeWorker(Protocol):
    async def probe(self, *, staging_key: str) -> VideoProbeResult: ...


class DurableVideoStore(Protocol):
    async def promote(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        staged: StagedProviderVideo,
        probe: VideoProbeResult,
    ) -> StoredVideoClip: ...

    async def discard_staging(self, staging_key: str) -> None: ...


class VerifiedVideoOutputAdapter:
    """Provider URLs stop at fetch_to_staging; durable stages use internal keys/checksums only."""

    def __init__(
        self,
        *,
        fetcher: ProviderVideoFetcher,
        probe_worker: VideoProbeWorker,
        store: DurableVideoStore,
    ) -> None:
        self.fetcher = fetcher
        self.probe_worker = probe_worker
        self.store = store

    async def materialize_and_probe(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        output_ref: str,
        declared_mime_type: str | None,
    ) -> tuple[StoredVideoClip, VideoProbeResult]:
        if not output_ref:
            raise ValueError("VIDEO_PROVIDER_OUTPUT_REF_REQUIRED")
        staged = await self.fetcher.fetch_to_staging(
            source_ref=output_ref,
            declared_mime_type=declared_mime_type,
            max_bytes=MAX_PROVIDER_VIDEO_BYTES,
        )
        try:
            if declared_mime_type is not None and declared_mime_type != "video/mp4":
                raise ValueError("VIDEO_PROVIDER_DECLARED_MIME_UNSUPPORTED")
            if staged.declared_mime_type is not None and staged.declared_mime_type != "video/mp4":
                raise ValueError("VIDEO_STAGED_MIME_UNSUPPORTED")
            probe = await self.probe_worker.probe(staging_key=staged.staging_key)
            if not probe.decode_ok:
                raise ValueError("VIDEO_PROVIDER_OUTPUT_NOT_DECODABLE")
            if probe.mime_type != "video/mp4" or probe.container.casefold() not in {"mp4", "mov,mp4,m4a,3gp,3g2,mj2"}:
                raise ValueError("VIDEO_PROVIDER_CONTAINER_UNSUPPORTED")
            stored = await self.store.promote(spec=spec, shot=shot, staged=staged, probe=probe)
            if stored.checksum_sha256 != staged.checksum_sha256:
                raise ValueError("VIDEO_DURABLE_CHECKSUM_MISMATCH")
            if stored.size_bytes != staged.size_bytes:
                raise ValueError("VIDEO_DURABLE_SIZE_MISMATCH")
            if stored.width != probe.width or stored.height != probe.height:
                raise ValueError("VIDEO_DURABLE_GEOMETRY_MISMATCH")
            return stored, probe
        finally:
            await self.store.discard_staging(staged.staging_key)
