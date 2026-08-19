from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .http_transport import HttpModelGatewayClient, encode_model_request, sign_internal_request
from .models import CostConfidence, CostEstimate, ModelRequest, RouteCandidate

_ESTIMATE_PATH = "/internal/v1/models/estimate"


@dataclass(frozen=True, slots=True)
class HttpRouteEstimate:
    provider: str
    model: str
    amount_usd: Decimal | None
    confidence: CostConfidence
    price_snapshot_id: str | None
    reason_codes: tuple[str, ...]

    def to_candidate(self) -> RouteCandidate:
        return RouteCandidate(
            provider=self.provider,
            model=self.model,
            estimate=CostEstimate(
                amount_usd=self.amount_usd,
                confidence=self.confidence,
                price_snapshot_id=self.price_snapshot_id,
            ),
            score=0,
            reason_codes=self.reason_codes,
        )


class HttpModelGatewayEstimateClient(HttpModelGatewayClient):
    """Signed, provider-neutral route estimate client for internal callers."""

    async def estimate(self, request: ModelRequest) -> HttpRouteEstimate:
        body = json.dumps(
            encode_model_request(request),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        auth = sign_internal_request(
            secret=self.auth_secret,
            service=self.caller_service,
            method="POST",
            path=_ESTIMATE_PATH,
            body=body,
        )
        payload = await asyncio.to_thread(
            self._request,
            _ESTIMATE_PATH,
            body,
            auth.as_dict(),
        )
        return decode_route_estimate(payload)


def encode_route_candidate(candidate: RouteCandidate) -> dict[str, Any]:
    return {
        "provider": candidate.provider,
        "model": candidate.model,
        "estimate": {
            "amount_usd": (
                format(candidate.estimate.amount_usd, "f")
                if candidate.estimate.amount_usd is not None
                else None
            ),
            "confidence": candidate.estimate.confidence.value,
            "price_snapshot_id": candidate.estimate.price_snapshot_id,
        },
        "reason_codes": list(candidate.reason_codes),
    }


def decode_route_estimate(payload: dict[str, Any]) -> HttpRouteEstimate:
    provider = payload.get("provider")
    model = payload.get("model")
    estimate = payload.get("estimate")
    reasons = payload.get("reason_codes")
    if not isinstance(provider, str) or not provider:
        raise ValueError("MODEL_GATEWAY_ESTIMATE_PROVIDER_INVALID")
    if not isinstance(model, str) or not model:
        raise ValueError("MODEL_GATEWAY_ESTIMATE_MODEL_INVALID")
    if not isinstance(estimate, dict):
        raise ValueError("MODEL_GATEWAY_ESTIMATE_COST_INVALID")
    raw_amount = estimate.get("amount_usd")
    amount: Decimal | None
    if raw_amount is None:
        amount = None
    elif isinstance(raw_amount, str) and raw_amount:
        amount = Decimal(raw_amount)
        if not amount.is_finite() or amount < 0:
            raise ValueError("MODEL_GATEWAY_ESTIMATE_AMOUNT_INVALID")
    else:
        raise ValueError("MODEL_GATEWAY_ESTIMATE_AMOUNT_INVALID")
    confidence = estimate.get("confidence")
    if not isinstance(confidence, str):
        raise ValueError("MODEL_GATEWAY_ESTIMATE_CONFIDENCE_INVALID")
    price_snapshot_id = estimate.get("price_snapshot_id")
    if price_snapshot_id is not None and not isinstance(price_snapshot_id, str):
        raise ValueError("MODEL_GATEWAY_ESTIMATE_PRICE_SNAPSHOT_INVALID")
    if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
        raise ValueError("MODEL_GATEWAY_ESTIMATE_REASON_CODES_INVALID")
    return HttpRouteEstimate(
        provider=provider,
        model=model,
        amount_usd=amount,
        confidence=CostConfidence(confidence),
        price_snapshot_id=price_snapshot_id,
        reason_codes=tuple(reasons),
    )
