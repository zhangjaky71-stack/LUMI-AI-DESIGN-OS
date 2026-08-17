from __future__ import annotations

import binascii
import struct
import zlib
from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid5

from .model import (
    AuthorizedReference,
    FetchedImage,
    GatewayRequest,
    GatewayResult,
    GatewayStatus,
    GenerationCandidate,
    GenerationProvenance,
    ImageGenerationSpec,
    StoredImage,
    ValidatedImage,
    ValidationBundle,
)
from .ports import ArtifactCandidateResult, CostProjection, GatewayEstimate


def png_bytes(width: int, height: int, *, alpha: bool = True) -> bytes:
    color_type = 6 if alpha else 2
    channels = 4 if alpha else 3
    pixel = bytes([0, 0, 0, 0] if alpha else [0, 0, 0])
    scan = b"".join(b"\x00" + pixel * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = binascii.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(
        b"IDAT", zlib.compress(scan)
    ) + chunk(b"IEND", b"")


class StaticReferenceAuthorizer:
    def __init__(self, values: tuple[AuthorizedReference, ...] = ()) -> None:
        self.values = values
        self.allowed = True
        self.calls = 0

    def authorize(self, spec: ImageGenerationSpec, references):
        self.calls += 1
        if not self.allowed:
            raise PermissionError("REFERENCE_RIGHTS_REVOKED")
        expected = {item.asset_id for item in references}
        actual = {item.asset_id for item in self.values}
        if expected != actual:
            raise PermissionError("REFERENCE_NOT_AUTHORIZED")
        if any(not item.commercial_use for item in self.values):
            raise PermissionError("REFERENCE_COMMERCIAL_USE_FORBIDDEN")
        return self.values


class FakeGateway:
    def __init__(self, *, cost: str = "0.01") -> None:
        self.cost = Decimal(cost)
        self.invocations = 0
        self.polls = 0
        self.pending = False
        self.poll_raises = False
        self.corrupt = False
        self.safety_block = False
        self.cancelled = False

    async def estimate(self, request: GatewayRequest) -> GatewayEstimate:
        return GatewayEstimate(
            self.cost,
            "pricing-v1",
            "mock",
            "mock-image-v1",
            "rev-1",
            "registry-v1",
            ("CAPABILITY_MATCH",),
        )

    async def invoke(self, request: GatewayRequest) -> GatewayResult:
        self.invocations += 1
        if self.pending:
            return GatewayResult(
                GatewayStatus.PENDING,
                "mock",
                "mock-image-v1",
                provider_request_id=f"pending-{request.variant_index}",
                model_revision="rev-1",
                registry_snapshot_id="registry-v1",
                cost_usd=self.cost,
                cost_confidence="exact",
                pricing_snapshot_id="pricing-v1",
                routing_reason_codes=("CAPABILITY_MATCH",),
                seed=request.seed,
            )
        return self._complete(request)

    def _complete(self, request: GatewayRequest) -> GatewayResult:
        return GatewayResult(
            GatewayStatus.COMPLETED,
            "mock",
            "mock-image-v1",
            outputs=(
                __import__("lumi_image_generation.model", fromlist=["ProviderOutputRef"])
                .ProviderOutputRef(f"fixture:{request.variant_index}", "image/png"),
            ),
            provider_request_id=f"mock-{request.variant_index}",
            model_revision="rev-1",
            registry_snapshot_id="registry-v1",
            cost_usd=self.cost,
            cost_confidence="exact",
            pricing_snapshot_id="pricing-v1",
            routing_reason_codes=("CAPABILITY_MATCH",),
            safety_metadata={"blocked": self.safety_block},
            seed=request.seed,
        )

    async def poll(
        self, *, request: GatewayRequest, pending_result: GatewayResult
    ) -> GatewayResult:
        self.polls += 1
        if self.poll_raises:
            raise TimeoutError("temporary")
        self.pending = False
        return self._complete(request)

    async def cancel(self, *, request: GatewayRequest, pending_result: GatewayResult) -> bool:
        del request, pending_result
        self.cancelled = True
        return True


class FixtureFetcher:
    def __init__(self, width: int, height: int, *, alpha: bool = True) -> None:
        self.content = png_bytes(width, height, alpha=alpha)
        self.corrupt = False

    async def fetch(self, ref: str, declared_mime_type: str | None) -> FetchedImage:
        return FetchedImage(
            ref,
            b"not-an-image" if self.corrupt else self.content,
            declared_mime_type,
        )


class MemoryStorage:
    async def store(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: UUID,
        image: ValidatedImage,
    ) -> StoredImage:
        return StoredImage(
            "generated",
            f"{spec.organization_id}/{candidate_id}.png",
            image.mime_type,
            image.width,
            image.height,
            len(image.content),
            image.checksum_sha256,
        )


class MemoryArtifacts:
    def __init__(self) -> None:
        self.values: list[tuple[GenerationCandidate, GenerationProvenance, ValidationBundle]] = []

    async def create_candidate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate: GenerationCandidate,
        stored: StoredImage,
        provenance: GenerationProvenance,
        validation: ValidationBundle,
    ) -> ArtifactCandidateResult:
        del spec, stored
        self.values.append((candidate, provenance, validation))
        artifact = uuid5(candidate.candidate_id, "artifact")
        version = uuid5(candidate.candidate_id, "artifact-version")
        return ArtifactCandidateResult(
            artifact,
            version,
            "DRAFT" if validation.hard_failed else "READY",
        )


class MemoryCosts:
    def __init__(self) -> None:
        self.values: list[CostProjection] = []

    async def record(self, projection: CostProjection) -> None:
        if not self.values or self.values[-1] != projection:
            self.values.append(projection)


class MemoryEvents:
    def __init__(self) -> None:
        self.values: list[tuple[str, dict[str, object]]] = []

    async def emit(self, event_type: str, *, organization_id, generation_id, payload) -> None:
        del organization_id, generation_id
        self.values.append((event_type, dict(payload)))


class MemoryWork:
    def __init__(self) -> None:
        self.values: list[tuple[UUID, UUID]] = []

    def publish(self, organization_id: UUID, generation_id: UUID) -> None:
        self.values.append((organization_id, generation_id))
