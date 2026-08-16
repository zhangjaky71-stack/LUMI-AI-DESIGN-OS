from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import (
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelTiming,
    ModelUsage,
    NormalizedResult,
    ResultStatus,
)


def result_to_dict(result: NormalizedResult) -> dict[str, Any]:
    timing = None
    if result.timing is not None:
        timing = {
            "total_ms": result.timing.total_ms,
            "ttft_ms": result.timing.ttft_ms,
        }
    return {
        "status": result.status.value,
        "provider": result.provider,
        "model": result.model,
        "outputs": [
            {
                "kind": output.kind,
                "text": output.text,
                "json_value": output.json_value,
                "asset_ref": output.asset_ref,
            }
            for output in result.outputs
        ],
        "provider_request_id": result.provider_request_id,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cached_input_tokens": result.usage.cached_input_tokens,
            "images": result.usage.images,
            "video_seconds": format(result.usage.video_seconds, "f"),
            "requests": result.usage.requests,
        },
        "timing": timing,
        "safety_metadata": dict(result.safety_metadata),
        "finish_reason": result.finish_reason,
        "raw_response_ref": result.raw_response_ref,
        "cost": {
            "amount_usd": (
                None
                if result.cost.amount_usd is None
                else format(result.cost.amount_usd, "f")
            ),
            "confidence": result.cost.confidence.value,
            "pricing_snapshot_id": result.cost.pricing_snapshot_id,
            "detail": dict(result.cost.detail),
        },
    }


def result_from_dict(data: dict[str, Any]) -> NormalizedResult:
    usage_data = data.get("usage") or {}
    timing_data = data.get("timing")
    cost_data = data.get("cost") or {}
    amount_raw = cost_data.get("amount_usd")
    timing = None
    if timing_data is not None:
        timing = ModelTiming(
            total_ms=int(timing_data["total_ms"]),
            ttft_ms=(
                None
                if timing_data.get("ttft_ms") is None
                else int(timing_data["ttft_ms"])
            ),
        )
    return NormalizedResult(
        status=ResultStatus(str(data["status"])),
        provider=str(data["provider"]),
        model=str(data["model"]),
        outputs=tuple(
            ModelOutput(
                kind=str(item["kind"]),
                text=item.get("text"),
                json_value=item.get("json_value"),
                asset_ref=item.get("asset_ref"),
            )
            for item in data.get("outputs") or []
        ),
        provider_request_id=data.get("provider_request_id"),
        usage=ModelUsage(
            input_tokens=int(usage_data.get("input_tokens") or 0),
            output_tokens=int(usage_data.get("output_tokens") or 0),
            cached_input_tokens=int(
                usage_data.get("cached_input_tokens") or 0
            ),
            images=int(usage_data.get("images") or 0),
            video_seconds=Decimal(
                str(usage_data.get("video_seconds") or "0")
            ),
            requests=int(usage_data.get("requests") or 1),
        ),
        timing=timing,
        safety_metadata=dict(data.get("safety_metadata") or {}),
        finish_reason=data.get("finish_reason"),
        raw_response_ref=data.get("raw_response_ref"),
        cost=CostEstimate(
            None if amount_raw is None else Decimal(str(amount_raw)),
            CostConfidence(
                str(cost_data.get("confidence") or "unknown")
            ),
            cost_data.get("pricing_snapshot_id"),
            dict(cost_data.get("detail") or {}),
        ),
    )
