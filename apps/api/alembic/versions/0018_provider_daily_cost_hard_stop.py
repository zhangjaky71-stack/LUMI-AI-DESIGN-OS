"""Add platform-wide provider daily USD hard-stop enforcement.

Revision ID: 0018_provider_daily_cost_hard_stop
Revises: 0017_knowledge_engine

The control is intentionally enforced in PostgreSQL before a cost reservation can
become active.  This keeps the denial-of-wallet boundary durable across API/model
Gateway process restarts and serializes concurrent reservations across tenants.
Production activation is explicit: operators configure provider caps first, then
flip the singleton policy row.  Once enabled, a missing provider cap fails closed.
"""

from __future__ import annotations

from alembic import op

revision = "0018_provider_daily_cost_hard_stop"
down_revision = "0017_knowledge_engine"
branch_labels = None
depends_on = None


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE platform_cost_controls (
        id smallint PRIMARY KEY DEFAULT 1,
        provider_daily_hard_stop_enabled boolean NOT NULL DEFAULT false,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_platform_cost_controls_singleton CHECK (id = 1),
        CONSTRAINT ck_platform_cost_controls_version CHECK (version > 0)
    )
    """,
    """
    INSERT INTO platform_cost_controls (
        id, provider_daily_hard_stop_enabled, metadata_json,
        created_at, updated_at, version
    ) VALUES (1, false, '{}'::jsonb, now(), now(), 1)
    """,
    """
    CREATE TABLE provider_daily_cost_limits (
        provider varchar(100) PRIMARY KEY,
        amount_limit_usd numeric(20,8) NOT NULL,
        enabled boolean NOT NULL DEFAULT true,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_provider_daily_cost_limits_provider CHECK (
            length(btrim(provider)) BETWEEN 1 AND 100
        ),
        CONSTRAINT ck_provider_daily_cost_limits_amount CHECK (
            amount_limit_usd >= 0
        ),
        CONSTRAINT ck_provider_daily_cost_limits_version CHECK (version > 0)
    )
    """,
    "ALTER TABLE cost_reservations ADD COLUMN budget_day_utc date",
    """
    UPDATE cost_reservations
    SET budget_day_utc = (created_at AT TIME ZONE 'UTC')::date
    WHERE budget_day_utc IS NULL
    """,
    "ALTER TABLE cost_reservations ALTER COLUMN budget_day_utc SET NOT NULL",
    "ALTER TABLE cost_ledger ADD COLUMN budget_day_utc date",
    "ALTER TABLE cost_ledger DISABLE TRIGGER trg_cost_ledger_immutable",
    """
    UPDATE cost_ledger
    SET budget_day_utc = (occurred_at AT TIME ZONE 'UTC')::date
    WHERE budget_day_utc IS NULL
    """,
    "ALTER TABLE cost_ledger ENABLE TRIGGER trg_cost_ledger_immutable",
    "ALTER TABLE cost_ledger ALTER COLUMN budget_day_utc SET NOT NULL",
    """
    CREATE INDEX ix_cost_reservations_provider_day_active
    ON cost_reservations (
        provider, budget_day_utc, currency, status, expires_at
    )
    """,
    """
    CREATE INDEX ix_cost_ledger_provider_day_actual
    ON cost_ledger (provider, budget_day_utc, currency)
    WHERE cost_basis='provider_cost' AND entry_type='actual_cost'
    """,
    """
    CREATE FUNCTION lumi_provider_daily_hard_stop()
    RETURNS trigger
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public, pg_temp
    SET row_security = off
    AS $$
    DECLARE
        enforcement_enabled boolean;
        hard_limit numeric(20,8);
        committed_amount numeric(20,8);
        active_amount numeric(20,8);
        utc_day date := (now() AT TIME ZONE 'UTC')::date;
    BEGIN
        -- budget_day_utc is assigned by the database.  Callers cannot move an
        -- active reservation to another day to evade the cap.
        IF TG_OP = 'INSERT' THEN
            NEW.budget_day_utc := utc_day;
        ELSIF NEW.status = 'active' AND OLD.status IS DISTINCT FROM 'active' THEN
            NEW.budget_day_utc := utc_day;
        ELSE
            NEW.budget_day_utc := OLD.budget_day_utc;
        END IF;

        IF NEW.status <> 'active' THEN
            RETURN NEW;
        END IF;

        SELECT provider_daily_hard_stop_enabled
        INTO enforcement_enabled
        FROM platform_cost_controls
        WHERE id = 1;

        IF COALESCE(enforcement_enabled, false) = false THEN
            RETURN NEW;
        END IF;

        IF NEW.currency <> 'USD' THEN
            RAISE EXCEPTION 'COST_PROVIDER_DAILY_CURRENCY_UNSUPPORTED provider=% currency=%',
                NEW.provider, NEW.currency
                USING ERRCODE = 'P0001';
        END IF;

        IF NEW.provider IS NULL OR length(btrim(NEW.provider)) = 0 THEN
            RAISE EXCEPTION 'COST_PROVIDER_DAILY_PROVIDER_REQUIRED'
                USING ERRCODE = 'P0001';
        END IF;

        -- Serialize all tenants for the same provider/day.  The lock name is
        -- deterministic and UTC-scoped, so concurrent reservations cannot both
        -- observe the same remaining amount and oversubscribe it.
        PERFORM pg_advisory_xact_lock(
            hashtextextended(
                'provider-daily:' || NEW.provider || ':' || NEW.budget_day_utc::text,
                0
            )
        );

        SELECT amount_limit_usd
        INTO hard_limit
        FROM provider_daily_cost_limits
        WHERE provider = NEW.provider AND enabled
        FOR SHARE;

        IF hard_limit IS NULL THEN
            RAISE EXCEPTION 'COST_PROVIDER_DAILY_LIMIT_NOT_CONFIGURED provider=%',
                NEW.provider
                USING ERRCODE = 'P0001';
        END IF;

        SELECT COALESCE(sum(amount), 0)
        INTO committed_amount
        FROM cost_ledger
        WHERE cost_basis = 'provider_cost'
          AND entry_type = 'actual_cost'
          AND provider = NEW.provider
          AND currency = 'USD'
          AND budget_day_utc = NEW.budget_day_utc;

        SELECT COALESCE(sum(estimated_amount), 0)
        INTO active_amount
        FROM cost_reservations
        WHERE provider = NEW.provider
          AND currency = 'USD'
          AND budget_day_utc = NEW.budget_day_utc
          AND status = 'active'
          AND expires_at > now()
          AND id <> NEW.id;

        IF committed_amount + active_amount + NEW.estimated_amount > hard_limit THEN
            RAISE EXCEPTION
                'COST_PROVIDER_DAILY_BUDGET_EXCEEDED provider=% day=% committed=% active=% requested=% limit=%',
                NEW.provider,
                NEW.budget_day_utc,
                committed_amount,
                active_amount,
                NEW.estimated_amount,
                hard_limit
                USING ERRCODE = 'P0001';
        END IF;

        RETURN NEW;
    END;
    $$
    """,
    """
    CREATE FUNCTION lumi_assign_cost_budget_day()
    RETURNS trigger
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public, pg_temp
    SET row_security = off
    AS $$
    DECLARE
        reservation_day date;
        enforcement_enabled boolean;
    BEGIN
        SELECT provider_daily_hard_stop_enabled
        INTO enforcement_enabled
        FROM platform_cost_controls
        WHERE id = 1;

        IF NEW.entry_type = 'actual_cost' THEN
            IF NEW.operation_id IS NOT NULL AND NEW.provider IS NOT NULL THEN
                SELECT budget_day_utc
                INTO reservation_day
                FROM cost_reservations
                WHERE operation_id = NEW.operation_id
                  AND provider = NEW.provider
                  AND model IS NOT DISTINCT FROM NEW.model
                  AND status IN ('active', 'expired', 'committed')
                ORDER BY
                    CASE status
                        WHEN 'active' THEN 0
                        WHEN 'expired' THEN 1
                        ELSE 2
                    END,
                    created_at DESC
                LIMIT 1;
            END IF;

            IF reservation_day IS NULL
               AND COALESCE(enforcement_enabled, false) THEN
                RAISE EXCEPTION
                    'COST_PROVIDER_DAILY_RESERVATION_REQUIRED operation=% provider=% model=%',
                    NEW.operation_id, NEW.provider, NEW.model
                    USING ERRCODE = 'P0001';
            END IF;

            NEW.budget_day_utc := COALESCE(
                reservation_day,
                (NEW.occurred_at AT TIME ZONE 'UTC')::date
            );
        ELSE
            NEW.budget_day_utc := (NEW.occurred_at AT TIME ZONE 'UTC')::date;
        END IF;

        RETURN NEW;
    END;
    $$
    """,
    """
    CREATE TRIGGER trg_cost_reservations_provider_daily_hard_stop
    BEFORE INSERT OR UPDATE ON cost_reservations
    FOR EACH ROW EXECUTE FUNCTION lumi_provider_daily_hard_stop()
    """,
    """
    CREATE TRIGGER trg_cost_ledger_assign_budget_day
    BEFORE INSERT ON cost_ledger
    FOR EACH ROW EXECUTE FUNCTION lumi_assign_cost_budget_day()
    """,
    "REVOKE ALL ON platform_cost_controls, provider_daily_cost_limits FROM lumi_app",
    "GRANT SELECT ON platform_cost_controls, provider_daily_cost_limits TO lumi_app",
    "REVOKE ALL ON FUNCTION lumi_provider_daily_hard_stop() FROM PUBLIC",
    "REVOKE ALL ON FUNCTION lumi_assign_cost_budget_day() FROM PUBLIC",
)


DOWNGRADE_STATEMENTS = (
    "DROP TRIGGER IF EXISTS trg_cost_ledger_assign_budget_day ON cost_ledger",
    "DROP TRIGGER IF EXISTS trg_cost_reservations_provider_daily_hard_stop ON cost_reservations",
    "DROP FUNCTION IF EXISTS lumi_assign_cost_budget_day()",
    "DROP FUNCTION IF EXISTS lumi_provider_daily_hard_stop()",
    "DROP INDEX IF EXISTS ix_cost_ledger_provider_day_actual",
    "DROP INDEX IF EXISTS ix_cost_reservations_provider_day_active",
    "ALTER TABLE cost_ledger DROP COLUMN budget_day_utc",
    "ALTER TABLE cost_reservations DROP COLUMN budget_day_utc",
    "DROP TABLE provider_daily_cost_limits",
    "DROP TABLE platform_cost_controls",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
