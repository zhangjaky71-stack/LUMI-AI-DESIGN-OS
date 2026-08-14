from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol

from .model import (
    AuthorizedReference,
    FetchedImage,
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GenerationCandidate,
    GenerationJob,
    GenerationProvenanceSnapshot,
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
    routing_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.amount_usd, float):
            raise ValueError("GENERATION_GATEWAY_ESTIMATE_FLOAT_FORBIDDEN")
        if not self.amount_usd.is_finite() or self.amount_usd < 0:
            raise ValueError("GENERATION_GATEWAY_ESTIMATE_INVALID")


@dataclass(frozen=True, slots=True)
class ArtifactCandidateResult:
    artifact_id: str
    artifact_version_id: str
    status: str


@dataclass(frozen=True, slots=True)
class PendingInvocationRecord:
    organization_id: str
    generation_id: str
    candidate_id: str
    variant_index: int
    request: GatewayGenerationRequest
    result: GatewayGenerationResult

    def __post_init__(self) -> None:
        if self.result.status != "PENDING":
            raise ValueError("PENDING_INVOCATION_REQUIRES_PENDING_RESULT")
        if not self.result.provider_request_id:
            raise ValueError("PENDING_INVOCATION_PROVIDER_REQUEST_REQUIRED")


class ReferenceAuthorizationPort(Protocol):
    def authorize(
        self,
        spec: ImageGenerationSpec,
        references: tuple[ImageReference, ...],
    ) -> tuple[AuthorizedReference, ...]: ...


class ImageModelGatewayPort(Protocol):
    async def estimate(self, request: GatewayGenerationRequest) -> GatewayEstimate: ...

    async def invoke(self, request: GatewayGenerationRequest) -> GatewayGenerationResult: ...

    async def poll(
        self,
        *,
        request: GatewayGenerationRequest,
        pending_result: GatewayGenerationResult,
    ) -> GatewayGenerationResult: ...


class ProviderOutputFetcherPort(Protocol):
    async def fetch(self, ref: str, declared_mime_type: str | None) -> FetchedImage: ...


class DurableImageStorePort(Protocol):
    async def store(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
    ) -> StoredImage: ...


class GenerationValidationPort(Protocol):
    async def validate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
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
        provenance: GenerationProvenanceSnapshot,
        validation: ValidationBundle,
    ) -> ArtifactCandidateResult: ...


class CostReconciliationPort(Protocol):
    async def record_generation_result(
        self,
        *,
        generation_id: str,
        candidate_id: str,
        operation_id: str,
        provider: str,
        model: str,
        provider_request_id: str | None,
        amount_usd: Decimal | None,
        confidence: str,
        pricing_snapshot_id: str | None,
    ) -> None: ...


class GenerationEventSinkPort(Protocol):
    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        generation_id: str,
        payload: Mapping[str, object],
    ) -> None: ...


class GenerationRepositoryPort(Protocol):
    def get_by_operation(self, organization_id: str, operation_id: str) -> GenerationJob | None: ...

    def save(self, job: GenerationJob) -> None: ...

    def get(self, organization_id: str, generation_id: str) -> GenerationJob | None: ...

    def save_spec(self, spec: ImageGenerationSpec) -> None: ...

    def get_spec(self, organization_id: str, operation_id: str) -> ImageGenerationSpec | None: ...

    def save_pending(self, record: PendingInvocationRecord) -> None: ...

    def get_pending(
        self,
        organization_id: str,
        generation_id: str,
        candidate_id: str,
    ) -> PendingInvocationRecord | None: ...

    def delete_pending(self, organization_id: str, generation_id: str, candidate_id: str) -> None: ...
