from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol
from uuid import UUID

from .model import (
    AuthorizedReference,
    FetchedImage,
    GatewayRequest,
    GatewayResult,
    GenerationCandidate,
    GenerationJob,
    GenerationProvenance,
    ImageGenerationSpec,
    ImageReference,
    StoredImage,
    ValidatedImage,
    ValidationBundle,
)


@dataclass(frozen=True, slots=True)
class GatewayEstimate:
    amount_usd: Decimal
    pricing_snapshot_id: str | None
    provider: str
    model: str
    model_revision: str | None = None
    registry_snapshot_id: str | None = None
    routing_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactCandidateResult:
    artifact_id: UUID
    artifact_version_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class PendingInvocation:
    organization_id: UUID
    generation_id: UUID
    candidate_id: UUID
    request: GatewayRequest
    result: GatewayResult
    queued_at: str
    last_polled_at: str | None = None
    poll_attempts: int = 0


@dataclass(frozen=True, slots=True)
class CostProjection:
    generation_id: UUID
    candidate_id: UUID
    operation_id: UUID
    provider: str
    model: str
    provider_request_id: str | None
    amount_usd: Decimal | None
    confidence: str
    pricing_snapshot_id: str | None


class ReferenceAuthorizationPort(Protocol):
    def authorize(
        self,
        spec: ImageGenerationSpec,
        references: tuple[ImageReference, ...],
    ) -> tuple[AuthorizedReference, ...]: ...


class ImageModelGatewayPort(Protocol):
    async def estimate(self, request: GatewayRequest) -> GatewayEstimate: ...

    async def invoke(self, request: GatewayRequest) -> GatewayResult: ...

    async def poll(
        self,
        *,
        request: GatewayRequest,
        pending_result: GatewayResult,
    ) -> GatewayResult: ...

    async def cancel(
        self,
        *,
        request: GatewayRequest,
        pending_result: GatewayResult,
    ) -> bool: ...


class ProviderOutputFetcherPort(Protocol):
    async def fetch(self, ref: str, declared_mime_type: str | None) -> FetchedImage: ...


class DurableImageStorePort(Protocol):
    async def store(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: UUID,
        image: ValidatedImage,
    ) -> StoredImage: ...


class GenerationValidationPort(Protocol):
    async def validate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: UUID,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> ValidationBundle: ...


class ArtifactCandidatePort(Protocol):
    async def create_candidate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate: GenerationCandidate,
        stored: StoredImage,
        provenance: GenerationProvenance,
        validation: ValidationBundle,
    ) -> ArtifactCandidateResult: ...


class CostProjectionPort(Protocol):
    async def record(self, projection: CostProjection) -> None: ...


class GenerationEventSinkPort(Protocol):
    async def emit(
        self,
        event_type: str,
        *,
        organization_id: UUID,
        generation_id: UUID,
        payload: Mapping[str, object],
    ) -> None: ...


class GenerationWorkPublisherPort(Protocol):
    def publish(self, organization_id: UUID, generation_id: UUID) -> None: ...


class GenerationRepositoryPort(Protocol):
    def get_by_operation(
        self, organization_id: UUID, operation_id: UUID
    ) -> GenerationJob | None: ...

    def save_spec(self, spec: ImageGenerationSpec) -> None: ...

    def get_spec(
        self, organization_id: UUID, operation_id: UUID
    ) -> ImageGenerationSpec | None: ...

    def save(self, job: GenerationJob) -> None: ...

    def get(self, organization_id: UUID, generation_id: UUID) -> GenerationJob | None: ...

    def save_pending(self, value: PendingInvocation) -> None: ...

    def get_pending(
        self, organization_id: UUID, generation_id: UUID, candidate_id: UUID
    ) -> PendingInvocation | None: ...

    def delete_pending(
        self, organization_id: UUID, generation_id: UUID, candidate_id: UUID
    ) -> None: ...
