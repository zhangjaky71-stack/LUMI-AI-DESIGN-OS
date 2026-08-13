from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .models import Capability, CostConfidence, CostEstimate, ModelRequest, Usage

_MILLION = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class PriceCard:
    snapshot_id: str
    input_usd_per_million_tokens: Decimal | None = None
    output_usd_per_million_tokens: Decimal | None = None
    image_usd_per_generation: Decimal | None = None
    video_usd_per_second: Decimal | None = None
    embedding_usd_per_million_tokens: Decimal | None = None

    def estimate(self, request: ModelRequest) -> CostEstimate:
        if request.capability in {
            Capability.LLM_REASONING,
            Capability.LLM_STRUCTURED_OUTPUT,
            Capability.LLM_VISION,
        }:
            if self.input_usd_per_million_tokens is None:
                return unknown_cost(self.snapshot_id)
            input_tokens = estimate_input_tokens(request.inputs)
            output_tokens = int(request.constraints.get("max_output_tokens", 1024))
            output_rate = self.output_usd_per_million_tokens
            if output_rate is None:
                return unknown_cost(self.snapshot_id)
            amount = (
                Decimal(input_tokens) * self.input_usd_per_million_tokens
                + Decimal(output_tokens) * output_rate
            ) / _MILLION
            return CostEstimate(
                amount_usd=amount,
                confidence=CostConfidence.ESTIMATED,
                price_snapshot_id=self.snapshot_id,
                detail={
                    "estimated_input_tokens": input_tokens,
                    "estimated_output_tokens": output_tokens,
                },
            )
        if request.capability in {
            Capability.IMAGE_GENERATE,
            Capability.IMAGE_EDIT,
            Capability.IMAGE_MASK_EDIT,
            Capability.IMAGE_REFERENCE_CONSISTENCY,
            Capability.IMAGE_TRANSPARENT_BACKGROUND,
        }:
            if self.image_usd_per_generation is None:
                return unknown_cost(self.snapshot_id)
            return CostEstimate(
                amount_usd=self.image_usd_per_generation,
                confidence=CostConfidence.ESTIMATED,
                price_snapshot_id=self.snapshot_id,
                detail={"generations": 1},
            )
        if request.capability in {
            Capability.VIDEO_TEXT_TO_VIDEO,
            Capability.VIDEO_IMAGE_TO_VIDEO,
            Capability.VIDEO_EDIT,
        }:
            if self.video_usd_per_second is None:
                return unknown_cost(self.snapshot_id)
            seconds = Decimal(str(request.constraints.get("duration_seconds", 5)))
            return CostEstimate(
                amount_usd=seconds * self.video_usd_per_second,
                confidence=CostConfidence.ESTIMATED,
                price_snapshot_id=self.snapshot_id,
                detail={"seconds": seconds},
            )
        if request.capability in {
            Capability.EMBEDDING_TEXT,
            Capability.EMBEDDING_MULTIMODAL,
        }:
            if self.embedding_usd_per_million_tokens is None:
                return unknown_cost(self.snapshot_id)
            input_tokens = estimate_input_tokens(request.inputs)
            amount = (
                Decimal(input_tokens) * self.embedding_usd_per_million_tokens
            ) / _MILLION
            return CostEstimate(
                amount_usd=amount,
                confidence=CostConfidence.ESTIMATED,
                price_snapshot_id=self.snapshot_id,
                detail={"estimated_input_tokens": input_tokens},
            )
        return unknown_cost(self.snapshot_id)

    def actual_from_usage(self, capability: Capability, usage: Usage) -> CostEstimate:
        if capability in {
            Capability.LLM_REASONING,
            Capability.LLM_STRUCTURED_OUTPUT,
            Capability.LLM_VISION,
        }:
            if (
                usage.input_tokens is None
                or usage.output_tokens is None
                or self.input_usd_per_million_tokens is None
                or self.output_usd_per_million_tokens is None
            ):
                return unknown_cost(self.snapshot_id)
            amount = (
                Decimal(usage.input_tokens) * self.input_usd_per_million_tokens
                + Decimal(usage.output_tokens) * self.output_usd_per_million_tokens
            ) / _MILLION
            return CostEstimate(
                amount_usd=amount,
                confidence=CostConfidence.EXACT,
                price_snapshot_id=self.snapshot_id,
                detail={
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                },
            )
        return unknown_cost(self.snapshot_id)


def estimate_input_tokens(inputs: dict[str, Any]) -> int:
    encoded = json.dumps(
        inputs,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return max(1, math.ceil(len(encoded) / 4))


def unknown_cost(snapshot_id: str | None = None) -> CostEstimate:
    return CostEstimate(
        amount_usd=None,
        confidence=CostConfidence.UNKNOWN,
        price_snapshot_id=snapshot_id,
    )
