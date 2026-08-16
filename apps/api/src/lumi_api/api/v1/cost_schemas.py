from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from .common import StrictModel


class CostSummaryResponse(StrictModel):
    organization_id: UUID
    project_id: UUID | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    actual_cost: Decimal
    adjustments: Decimal
    reversals: Decimal
    net_provider_cost: Decimal
    active_reservations: Decimal
    non_exact_entries: int = Field(ge=0)
    from_time: datetime
    to_time: datetime


class UsageSummaryItem(StrictModel):
    organization_id: UUID
    project_id: UUID | None = None
    metric: str
    quantity: Decimal = Field(ge=0)
    unit: str
    from_time: datetime
    to_time: datetime


class UsageSummaryResponse(StrictModel):
    items: list[UsageSummaryItem]
