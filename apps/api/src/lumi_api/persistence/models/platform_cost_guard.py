from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, MutableTimestampMixin


class PlatformProviderCostGuard(MutableTimestampMixin, Base):
    """Migration-owned singleton policy for the global provider USD/day boundary."""

    __tablename__ = "platform_provider_cost_guard"
    __table_args__ = (
        CheckConstraint(
            "daily_cap_usd > 0 AND daily_cap_usd <= 100.00000000",
            name="cap",
        ),
        CheckConstraint("length(policy_key) BETWEEN 1 AND 64", name="key"),
    )

    policy_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    daily_cap_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fail_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
