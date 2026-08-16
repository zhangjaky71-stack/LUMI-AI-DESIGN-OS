from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Index,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, MutableTimestampMixin
from .platform import CostLedger, CostReservation


def _extend_cost_tables() -> None:
    """Keep Alembic metadata aligned without changing the public ORM API.

    Cost reservation/ledger writes use the raw durable gateway. The database owns
    ``budget_day_utc`` through triggers, so these columns intentionally remain
    unmapped class attributes while still belonging to ``Base.metadata`` for the
    canonical ``alembic check`` drift gate.
    """

    ledger = CostLedger.__table__
    reservations = CostReservation.__table__

    if "budget_day_utc" not in ledger.c:
        ledger.append_column(Column("budget_day_utc", Date, nullable=False))
    if "budget_day_utc" not in reservations.c:
        reservations.append_column(Column("budget_day_utc", Date, nullable=False))

    ledger_index_names = {index.name for index in ledger.indexes}
    if "ix_cost_ledger_provider_day_actual" not in ledger_index_names:
        Index(
            "ix_cost_ledger_provider_day_actual",
            ledger.c.provider,
            ledger.c.budget_day_utc,
            ledger.c.currency,
            postgresql_where=text(
                "cost_basis='provider_cost' AND entry_type='actual_cost'"
            ),
        )

    reservation_index_names = {index.name for index in reservations.indexes}
    if "ix_cost_reservations_provider_day_active" not in reservation_index_names:
        Index(
            "ix_cost_reservations_provider_day_active",
            reservations.c.provider,
            reservations.c.budget_day_utc,
            reservations.c.currency,
            reservations.c.status,
            reservations.c.expires_at,
        )


_extend_cost_tables()


class PlatformCostControl(MutableTimestampMixin, Base):
    __tablename__ = "platform_cost_controls"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("version > 0", name="version"),
    )

    id: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        default=1,
        server_default="1",
    )
    provider_daily_hard_stop_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class ProviderDailyCostLimit(MutableTimestampMixin, Base):
    __tablename__ = "provider_daily_cost_limits"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(provider)) BETWEEN 1 AND 100",
            name="provider",
        ),
        CheckConstraint("amount_limit_usd >= 0", name="amount"),
        CheckConstraint("version > 0", name="version"),
    )

    provider: Mapped[str] = mapped_column(String(100), primary_key=True)
    amount_limit_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
