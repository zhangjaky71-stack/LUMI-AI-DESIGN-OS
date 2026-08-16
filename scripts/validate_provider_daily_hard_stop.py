from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "apps/api/alembic/versions/0018_provider_daily_cost_hard_stop.py"
ADAPTER = ROOT / "apps/api/src/lumi_api/costs/model_gateway_adapter.py"
ORM = ROOT / "apps/api/src/lumi_api/persistence/models/provider_cost_controls.py"
MODELS_INIT = ROOT / "apps/api/src/lumi_api/persistence/models/__init__.py"
INTEGRATION = ROOT / "scripts/integration_provider_daily_hard_stop.py"


def _require(text: str, needles: tuple[str, ...], *, source: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{source} missing required hard-stop contract: {missing}")


def main() -> int:
    migration = MIGRATION.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    orm = ORM.read_text(encoding="utf-8")
    models_init = MODELS_INIT.read_text(encoding="utf-8")
    integration = INTEGRATION.read_text(encoding="utf-8")

    _require(
        migration,
        (
            'down_revision = "0017_knowledge_engine"',
            "CREATE TABLE platform_cost_controls",
            "provider_daily_hard_stop_enabled boolean NOT NULL DEFAULT false",
            "CREATE TABLE provider_daily_cost_limits",
            "amount_limit_usd numeric(20,8) NOT NULL",
            "ALTER TABLE cost_reservations ADD COLUMN budget_day_utc date",
            "ALTER TABLE cost_ledger ADD COLUMN budget_day_utc date",
            "CREATE FUNCTION lumi_provider_daily_hard_stop()",
            "CREATE FUNCTION lumi_assign_cost_budget_day()",
            "SECURITY DEFINER",
            "SET row_security = off",
            "pg_advisory_xact_lock",
            "COST_PROVIDER_DAILY_LIMIT_NOT_CONFIGURED",
            "COST_PROVIDER_DAILY_BUDGET_EXCEEDED",
            "COST_PROVIDER_DAILY_RESERVATION_REQUIRED",
            "committed_amount + active_amount + NEW.estimated_amount > hard_limit",
            "REVOKE ALL ON platform_cost_controls, provider_daily_cost_limits FROM lumi_app",
            "GRANT SELECT ON platform_cost_controls, provider_daily_cost_limits TO lumi_app",
        ),
        source=str(MIGRATION),
    )
    if migration.count("pg_advisory_xact_lock") < 2:
        raise AssertionError(
            "provider admission and actual settlement must share the provider/day lock"
        )
    hard_stop_body = migration.split(
        "CREATE FUNCTION lumi_provider_daily_hard_stop()", 1
    )[1].split("CREATE FUNCTION lumi_assign_cost_budget_day()", 1)[0]
    if "organization_id =" in hard_stop_body:
        raise AssertionError("provider/day hard stop must aggregate across organizations")

    _require(
        adapter,
        (
            "_PROVIDER_DAILY_HARD_STOP_MARKERS",
            "except asyncpg.PostgresError as exc:",
            "_raise_provider_daily_budget_error(exc)",
            "raise BudgetExceeded(message) from exc",
        ),
        source=str(ADAPTER),
    )

    _require(
        orm,
        (
            'Column("budget_day_utc", Date, nullable=False)',
            '"ix_cost_ledger_provider_day_actual"',
            '"ix_cost_reservations_provider_day_active"',
            'class PlatformCostControl(MutableTimestampMixin, Base):',
            'class ProviderDailyCostLimit(MutableTimestampMixin, Base):',
            'mapped_column(Numeric(20, 8), nullable=False)',
        ),
        source=str(ORM),
    )
    _require(
        models_init,
        (
            "from .provider_cost_controls import PlatformCostControl, ProviderDailyCostLimit",
            '"PlatformCostControl"',
            '"ProviderDailyCostLimit"',
        ),
        source=str(MODELS_INIT),
    )

    _require(
        integration,
        (
            "missing provider limit",
            "exactly three 0.10 reservations may fit under 0.30",
            "assert globally_reserved == Decimal(\"0.30000000\")",
            "assert replay_ticket == exact_ticket",
            "assert tamper_day == original_day",
            "actual_amount_usd=Decimal(\"0.35\")",
            "post-actual overspend",
            "lumi_app must not mutate platform cost controls",
        ),
        source=str(INTEGRATION),
    )

    print("Provider daily USD hard-stop static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
