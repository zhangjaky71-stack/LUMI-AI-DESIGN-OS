from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable

from .contracts import ContextItem, ContextLayer, ContextRequest

TokenCounter = Callable[[str], int]


def conservative_token_estimate(text: str) -> int:
    if not text:
        return 0
    # Conservative language-neutral fallback; provider-specific counters can be injected.
    return max(1, math.ceil(len(text.encode("utf-8")) / 3))


def with_token_estimate(item: ContextItem, counter: TokenCounter) -> ContextItem:
    # Count the exact safety-rendered payload, not only raw content.
    from .safety import render_context_item

    return replace(item, token_estimate=counter(render_context_item(item)))


def layer_caps(request: ContextRequest) -> dict[ContextLayer, int]:
    caps = {item.layer: item.max_tokens for item in request.layer_budgets}
    if sum(caps.values()) > request.context_budget_tokens:
        # Per-layer caps are upper bounds; total assembly still enforces the hard global limit.
        return caps
    return caps
