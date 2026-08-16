from __future__ import annotations

import hashlib
from dataclasses import dataclass

from lumi_model_gateway.errors import ProviderAcceptance, ProviderCallError
from lumi_model_gateway.models import (
    Capability,
    ModelRequest,
    NormalizedResult,
    ResultStatus,
    RouteCandidate,
)
from lumi_model_gateway.ports import PaidEffect, ReconcileEffect
from lumi_model_gateway.serialization import result_from_dict, result_to_dict

from .idempotency.gateway import ProviderReconciler, SideEffectGateway
from .idempotency.models import (
    CompensationMode,
    IdempotencyOperation,
    OperationRequest,
    ProviderReconciliation,
    ProviderReconciliationStatus,
    SideEffectKind,
    SideEffectOutcome,
)

CONFIRMED_NOT_ACCEPTED_CODE = "SIDE_EFFECT_CONFIRMED_NOT_ACCEPTED"


class ConfirmedNotAcceptedProviderError(RuntimeError):
    code = CONFIRMED_NOT_ACCEPTED_CODE
    retryable = True

    def __init__(self, original: ProviderCallError) -> None:
        super().__init__(str(original))
        self.original = original


@dataclass(slots=True)
class _ModelProviderReconciler(ProviderReconciler):
    reconcile_effect: ReconcileEffect | None

    async def reconcile(
        self, operation: IdempotencyOperation
    ) -> ProviderReconciliation:
        if not operation.provider_request_id or self.reconcile_effect is None:
            return ProviderReconciliation(
                status=ProviderReconciliationStatus.AMBIGUOUS,
                provider_request_id=operation.provider_request_id,
                detail=(
                    "provider request id/status unavailable; paid effect cannot be safely "
                    "replayed"
                ),
            )
        try:
            result = await self.reconcile_effect(operation.provider_request_id)
        except Exception as exc:
            return ProviderReconciliation(
                status=ProviderReconciliationStatus.AMBIGUOUS,
                provider_request_id=operation.provider_request_id,
                detail=f"provider reconciliation failed: {type(exc).__name__}",
            )
        if result.status is ResultStatus.PENDING:
            return ProviderReconciliation(
                status=ProviderReconciliationStatus.RUNNING,
                provider_request_id=operation.provider_request_id,
            )
        if result.status is ResultStatus.COMPLETED:
            return ProviderReconciliation(
                status=ProviderReconciliationStatus.SUCCEEDED,
                provider_request_id=operation.provider_request_id,
                response_status=200,
                result=result_to_dict(result),
                result_ref=_first_asset_ref(result),
            )
        return ProviderReconciliation(
            status=ProviderReconciliationStatus.NOT_FOUND,
            provider_request_id=operation.provider_request_id,
            detail=(
                f"provider reports terminal non-success status {result.status.value}"
            ),
        )


class Node20ModelSideEffectBridge:
    """Binds NODE-22 paid model calls to NODE-20 durable idempotency semantics."""

    def __init__(
        self,
        gateway: SideEffectGateway,
        *,
        lease_owner: str,
        lease_seconds: int = 120,
        ttl_seconds: int = 86400,
    ) -> None:
        self.gateway = gateway
        self.lease_owner = lease_owner
        self.lease_seconds = lease_seconds
        self.ttl_seconds = ttl_seconds

    async def execute(
        self,
        *,
        request: ModelRequest,
        candidate: RouteCandidate,
        effect: PaidEffect,
        reconcile: ReconcileEffect | None = None,
    ) -> NormalizedResult:
        operation_request = OperationRequest(
            organization_id=request.organization_id,
            operation_type=f"model.invoke.{candidate.model.provider}",
            idempotency_key=f"{request.operation_id}:{candidate.model.model}",
            request_hash=_candidate_hash(request, candidate),
            business_scope_id=str(request.operation_id),
            side_effect_kind=_side_effect_kind(request.capability),
            compensation_mode=CompensationMode.NON_COMPENSATABLE,
            paid=True,
            lease_seconds=self.lease_seconds,
            ttl_seconds=self.ttl_seconds,
        )

        async def wrapped(context) -> SideEffectOutcome:
            try:
                result = await effect()
            except ProviderCallError as exc:
                if (
                    exc.retryable
                    and exc.acceptance is ProviderAcceptance.NOT_ACCEPTED
                ):
                    raise ConfirmedNotAcceptedProviderError(exc) from exc
                raise
            if result.provider_request_id:
                await context.record_provider_request(result.provider_request_id)
            return SideEffectOutcome(
                result=result_to_dict(result),
                result_ref=_first_asset_ref(result),
                response_status=(
                    202 if result.status is ResultStatus.PENDING else 200
                ),
                provider_request_id=result.provider_request_id,
            )

        reconciler = _ModelProviderReconciler(reconcile)
        try:
            outcome = await self.gateway.execute(
                operation_request,
                wrapped,
                lease_owner=self.lease_owner,
                reconciler=reconciler,
            )
        except ConfirmedNotAcceptedProviderError as exc:
            raise exc.original from exc
        return result_from_dict(outcome.result)


def _candidate_hash(request: ModelRequest, candidate: RouteCandidate) -> str:
    material = (
        f"{request.semantic_hash()}:{candidate.model.provider}:{candidate.model.model}"
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _side_effect_kind(capability: Capability) -> SideEffectKind:
    if capability.value.startswith("image."):
        return SideEffectKind.IMAGE_GENERATION
    if capability.value.startswith("video."):
        return SideEffectKind.VIDEO_GENERATION
    return SideEffectKind.PAID_MODEL_INVOCATION


def _first_asset_ref(result: NormalizedResult) -> str | None:
    return next(
        (output.asset_ref for output in result.outputs if output.asset_ref),
        None,
    )
