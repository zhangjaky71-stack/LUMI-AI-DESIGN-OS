from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RepairCostEstimate:
    amount_usd: Decimal
    provider: str
    model: str
    pricing_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        if self.amount_usd < 0:
            raise ValueError("REPAIR_COST_ESTIMATE_INVALID")
        if not self.provider or not self.model:
            raise ValueError("REPAIR_COST_ROUTE_REQUIRED")
