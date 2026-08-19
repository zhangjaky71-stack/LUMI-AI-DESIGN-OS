from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from .model import (
    AuthorizedReference,
    FetchedImage,
    GatewayGenerationRequest,
    GatewayGenerationResult,
    ImageGenerationSpec,
    ImageReference,
    StoredImage,
    ValidatedImage,
)
from .ports import GatewayEstimate


class StaticReferenceAuthorizer:
    def __init__(self, references: Mapping[tuple[str, str], AuthorizedReference]) -> None:
        self.references = dict(references)

    async def authorize(
        self,
        spec: ImageGenerationSpec,
        references: tuple[ImageReference, ...],
    ) -> tuple[AuthorizedReference, ...]:
        del spec
        result: list[AuthorizedReference] = []
        for reference in references:
            item = self.references.get((reference.asset_id, reference.asset_version))
            if item is None:
                raise ValueError("GENERATION_REFERENCE_NOT_ACCESSIBLE")
            if item.role != reference.role:
                item = AuthorizedReference(
                    asset_id=item.asset_id,
                    asset_version=item.asset_version,
                    role=reference.role,
                    source=reference.source,
                    durable_ref=item.durable_ref,
                    rights=item.rights,
                    commercial_use_allowed=item.commercial_use_allowed,
                    checksum_sha256=item.checksum_sha256,
                    mime_type=item.mime_type,
                    approval_state=item.approval_state,
                )
            result.append(item)
        return tuple(result)


class ScriptedImageGateway:
    def __init__(
        self,
        *,
        estimate: GatewayEstimate,
        results: tuple[GatewayGenerationResult, ...],
        poll_results: tuple[GatewayGenerationResult, ...] = (),
    ) -> None:
        self._estimate = estimate
        self._results = list(results)
        self._poll_results = list(poll_results)
        self.invoke_count = 0
        self.poll_count = 0
        self.requests: list[GatewayGenerationRequest] = []

    async def estimate(self, request: GatewayGenerationRequest) -> GatewayEstimate:
        self.requests.append(request)
        return self._estimate

    async def invoke(self, request: GatewayGenerationRequest) -> GatewayGenerationResult:
        self.invoke_count += 1
        self.requests.append(request)
        if not self._results:
            raise AssertionError("scripted gateway has no invoke result")
        return self._results.pop(0)

    async def poll(
        self,
        *,
        request: GatewayGenerationRequest,
        pending_result: GatewayGenerationResult,
    ) -> GatewayGenerationResult:
        self.poll_count += 1
        self.requests.append(request)
        if pending_result.status != "PENDING":
            raise AssertionError("poll expected pending result")
        if not self._poll_results:
            return pending_result
        return self._poll_results.pop(0)


class InMemoryOutputFetcher:
    def __init__(self, payloads: Mapping[str, bytes]) -> None:
        self.payloads = dict(payloads)

    async def fetch(self, ref: str, declared_mime_type: str | None) -> FetchedImage:
        try:
            content = self.payloads[ref]
        except KeyError as exc:
            raise ValueError("GENERATION_PROVIDER_OUTPUT_NOT_FOUND") from exc
        return FetchedImage(
            source_ref=ref,
            content=content,
            declared_mime_type=declared_mime_type,
        )


class InMemoryDurableImageStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def store(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
    ) -> StoredImage:
        storage_key = (
            f"org/{spec.organization_id}/project/{spec.project_id}/generation/"
            f"{candidate_id}/original"
        )
        checksum = hashlib.sha256(image.content).hexdigest()
        if checksum != image.checksum_sha256:
            raise ValueError("GENERATION_STORAGE_CHECKSUM_MISMATCH")
        self.objects[storage_key] = image.content
        return StoredImage(
            storage_key=storage_key,
            mime_type=image.mime_type,
            width=image.width,
            height=image.height,
            size_bytes=len(image.content),
            checksum_sha256=checksum,
        )


@dataclass(frozen=True, slots=True)
class CostRecord:
    generation_id: str
    candidate_id: str
    operation_id: str
    provider: str
    model: str
    provider_request_id: str | None
    amount_usd: Decimal | None
    confidence: str
    pricing_snapshot_id: str | None


class InMemoryCostReconciliation:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], CostRecord] = {}

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
    ) -> None:
        key = (generation_id, candidate_id)
        record = CostRecord(
            generation_id=generation_id,
            candidate_id=candidate_id,
            operation_id=operation_id,
            provider=provider,
            model=model,
            provider_request_id=provider_request_id,
            amount_usd=amount_usd,
            confidence=confidence,
            pricing_snapshot_id=pricing_snapshot_id,
        )
        existing = self.records.get(key)
        if existing is not None and existing != record:
            raise ValueError("GENERATION_COST_RECONCILIATION_CONFLICT")
        self.records[key] = record


@dataclass(frozen=True, slots=True)
class EmittedEvent:
    event_type: str
    organization_id: str
    generation_id: str
    payload: Mapping[str, object]


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[EmittedEvent] = []

    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        generation_id: str,
        payload: Mapping[str, object],
    ) -> None:
        self.events.append(
            EmittedEvent(
                event_type=event_type,
                organization_id=organization_id,
                generation_id=generation_id,
                payload=dict(payload),
            )
        )
