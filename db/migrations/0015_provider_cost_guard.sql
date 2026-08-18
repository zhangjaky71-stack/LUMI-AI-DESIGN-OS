BEGIN;

-- NODE-27 / Release Closure P0: one canonical provider-dollar hard stop shared by
-- every ModelGateway capability. The cap is snapshotted into each UTC day so a
-- mid-day policy edit cannot silently change already-reserved accounting truth.
CREATE TABLE IF NOT EXISTS provider_cost_guard_policy (
  policy_key text PRIMARY KEY,
  currency char(3) NOT NULL CHECK (currency = 'USD'),
  daily_cap_usd numeric(20,8) NOT NULL CHECK (daily_cap_usd > 0),
  enabled boolean NOT NULL DEFAULT true,
  fail_closed boolean NOT NULL DEFAULT true,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text NOT NULL
);

INSERT INTO provider_cost_guard_policy
  (policy_key, currency, daily_cap_usd, enabled, fail_closed, updated_by)
VALUES
  ('platform', 'USD', 100.00000000, true, true, 'system:release-closure-p0')
ON CONFLICT (policy_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS provider_cost_daily_usage (
  budget_date date PRIMARY KEY,
  currency char(3) NOT NULL CHECK (currency = 'USD'),
  cap_usd numeric(20,8) NOT NULL CHECK (cap_usd > 0),
  reserved_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0),
  committed_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (committed_usd >= 0),
  breached_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provider_cost_reservations (
  reservation_ticket uuid PRIMARY KEY,
  budget_date date NOT NULL REFERENCES provider_cost_daily_usage(budget_date),
  organization_id uuid NOT NULL,
  operation_id uuid NOT NULL,
  project_id uuid NULL,
  task_id uuid NULL,
  agent_run_id uuid NULL,
  generation_id uuid NULL,
  provider text NOT NULL,
  model text NOT NULL,
  reservation_key text NOT NULL,
  estimated_amount_usd numeric(20,8) NOT NULL CHECK (estimated_amount_usd > 0),
  actual_amount_usd numeric(20,8) NULL CHECK (actual_amount_usd IS NULL OR actual_amount_usd >= 0),
  confidence text NOT NULL,
  pricing_snapshot_id text NULL,
  provider_request_id text NULL,
  usage_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(usage_json) = 'object'),
  status text NOT NULL CHECK (status IN ('RESERVED','COMMITTED','RELEASED')),
  release_reason text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  finalized_at timestamptz NULL,
  UNIQUE (organization_id, operation_id, reservation_key)
);
CREATE INDEX IF NOT EXISTS provider_cost_reservations_day_status_idx
  ON provider_cost_reservations (budget_date, status);
CREATE INDEX IF NOT EXISTS provider_cost_reservations_provider_idx
  ON provider_cost_reservations (provider, model, created_at DESC);
CREATE INDEX IF NOT EXISTS provider_cost_reservations_generation_idx
  ON provider_cost_reservations (generation_id)
  WHERE generation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS provider_cost_ledger (
  ledger_id bigserial PRIMARY KEY,
  reservation_ticket uuid NOT NULL REFERENCES provider_cost_reservations(reservation_ticket),
  budget_date date NOT NULL,
  organization_id uuid NOT NULL,
  operation_id uuid NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  entry_type text NOT NULL CHECK (entry_type IN ('RESERVATION','ACTUAL_COST','RESERVATION_RELEASE','ADJUSTMENT','REVERSAL')),
  amount_usd numeric(20,8) NOT NULL CHECK (amount_usd >= 0),
  confidence text NOT NULL,
  pricing_snapshot_id text NULL,
  provider_request_id text NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS provider_cost_ledger_day_idx
  ON provider_cost_ledger (budget_date, occurred_at, ledger_id);
CREATE INDEX IF NOT EXISTS provider_cost_ledger_org_idx
  ON provider_cost_ledger (organization_id, occurred_at DESC, ledger_id DESC);
CREATE INDEX IF NOT EXISTS provider_cost_ledger_operation_idx
  ON provider_cost_ledger (operation_id, occurred_at, ledger_id);

CREATE OR REPLACE FUNCTION provider_cost_reserve(
  p_organization_id uuid,
  p_operation_id uuid,
  p_project_id uuid,
  p_task_id uuid,
  p_agent_run_id uuid,
  p_generation_id uuid,
  p_provider text,
  p_model text,
  p_estimated_amount_usd numeric,
  p_confidence text,
  p_pricing_snapshot_id text,
  p_reservation_key text,
  p_proposed_ticket uuid
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_day date := (clock_timestamp() AT TIME ZONE 'UTC')::date;
  v_cap numeric(20,8);
  v_enabled boolean;
  v_fail_closed boolean;
  v_reserved numeric(20,8);
  v_committed numeric(20,8);
  v_existing provider_cost_reservations%ROWTYPE;
BEGIN
  IF p_estimated_amount_usd IS NULL OR p_estimated_amount_usd <= 0 THEN
    RAISE EXCEPTION 'COST_INVALID_ESTIMATE';
  END IF;
  IF p_provider IS NULL OR btrim(p_provider) = '' OR p_model IS NULL OR btrim(p_model) = '' THEN
    RAISE EXCEPTION 'COST_PROVIDER_IDENTITY_REQUIRED';
  END IF;

  SELECT daily_cap_usd, enabled, fail_closed
    INTO v_cap, v_enabled, v_fail_closed
  FROM provider_cost_guard_policy
  WHERE policy_key = 'platform'
  FOR SHARE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'COST_GUARD_POLICY_MISSING';
  END IF;
  IF NOT v_fail_closed THEN
    RAISE EXCEPTION 'COST_GUARD_FAIL_CLOSED_REQUIRED';
  END IF;
  IF NOT v_enabled THEN
    RAISE EXCEPTION 'COST_GUARD_DISABLED';
  END IF;

  INSERT INTO provider_cost_daily_usage
    (budget_date, currency, cap_usd, reserved_usd, committed_usd)
  VALUES
    (v_day, 'USD', v_cap, 0, 0)
  ON CONFLICT (budget_date) DO NOTHING;

  -- This row lock is the platform-wide serialization point. Every paid request
  -- for the same UTC day competes on one row, preventing concurrent overspend.
  SELECT reserved_usd, committed_usd
    INTO v_reserved, v_committed
  FROM provider_cost_daily_usage
  WHERE budget_date = v_day
  FOR UPDATE;

  SELECT * INTO v_existing
  FROM provider_cost_reservations
  WHERE organization_id = p_organization_id
    AND operation_id = p_operation_id
    AND reservation_key = p_reservation_key;

  IF FOUND THEN
    IF v_existing.provider <> p_provider
       OR v_existing.model <> p_model
       OR v_existing.estimated_amount_usd <> p_estimated_amount_usd THEN
      RAISE EXCEPTION 'COST_IDEMPOTENCY_COLLISION';
    END IF;
    RETURN v_existing.reservation_ticket;
  END IF;

  IF v_committed + v_reserved + p_estimated_amount_usd > v_cap THEN
    RAISE EXCEPTION 'COST_DAILY_CAP_EXCEEDED';
  END IF;

  INSERT INTO provider_cost_reservations (
    reservation_ticket, budget_date, organization_id, operation_id,
    project_id, task_id, agent_run_id, generation_id, provider, model,
    reservation_key, estimated_amount_usd, confidence, pricing_snapshot_id,
    status
  ) VALUES (
    p_proposed_ticket, v_day, p_organization_id, p_operation_id,
    p_project_id, p_task_id, p_agent_run_id, p_generation_id, p_provider, p_model,
    p_reservation_key, p_estimated_amount_usd, p_confidence, p_pricing_snapshot_id,
    'RESERVED'
  );

  UPDATE provider_cost_daily_usage
  SET reserved_usd = reserved_usd + p_estimated_amount_usd,
      updated_at = clock_timestamp()
  WHERE budget_date = v_day;

  INSERT INTO provider_cost_ledger (
    reservation_ticket, budget_date, organization_id, operation_id,
    provider, model, entry_type, amount_usd, confidence, pricing_snapshot_id,
    metadata
  ) VALUES (
    p_proposed_ticket, v_day, p_organization_id, p_operation_id,
    p_provider, p_model, 'RESERVATION', p_estimated_amount_usd, p_confidence,
    p_pricing_snapshot_id, jsonb_build_object('reservation_key', p_reservation_key)
  );

  RETURN p_proposed_ticket;
END;
$$;

CREATE OR REPLACE FUNCTION provider_cost_commit(
  p_reservation_ticket uuid,
  p_actual_amount_usd numeric,
  p_confidence text,
  p_pricing_snapshot_id text,
  p_provider_request_id text,
  p_usage_json jsonb
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_reservation provider_cost_reservations%ROWTYPE;
BEGIN
  IF p_actual_amount_usd IS NULL OR p_actual_amount_usd < 0 THEN
    RAISE EXCEPTION 'COST_INVALID_ACTUAL';
  END IF;
  IF p_usage_json IS NULL OR jsonb_typeof(p_usage_json) <> 'object' THEN
    RAISE EXCEPTION 'COST_USAGE_JSON_INVALID';
  END IF;

  SELECT * INTO v_reservation
  FROM provider_cost_reservations
  WHERE reservation_ticket = p_reservation_ticket
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'COST_RESERVATION_NOT_FOUND';
  END IF;
  IF v_reservation.status = 'RELEASED' THEN
    RAISE EXCEPTION 'COST_RESERVATION_RELEASED';
  END IF;
  IF v_reservation.status = 'COMMITTED' THEN
    IF v_reservation.actual_amount_usd <> p_actual_amount_usd
       OR COALESCE(v_reservation.provider_request_id, '') <> COALESCE(p_provider_request_id, '') THEN
      RAISE EXCEPTION 'COST_IDEMPOTENCY_COLLISION';
    END IF;
    RETURN p_reservation_ticket;
  END IF;

  PERFORM 1
  FROM provider_cost_daily_usage
  WHERE budget_date = v_reservation.budget_date
  FOR UPDATE;

  UPDATE provider_cost_daily_usage
  SET reserved_usd = GREATEST(0, reserved_usd - v_reservation.estimated_amount_usd),
      committed_usd = committed_usd + p_actual_amount_usd,
      breached_at = CASE
        WHEN committed_usd + p_actual_amount_usd
             + GREATEST(0, reserved_usd - v_reservation.estimated_amount_usd) > cap_usd
          THEN COALESCE(breached_at, clock_timestamp())
        ELSE breached_at
      END,
      updated_at = clock_timestamp()
  WHERE budget_date = v_reservation.budget_date;

  UPDATE provider_cost_reservations
  SET actual_amount_usd = p_actual_amount_usd,
      confidence = p_confidence,
      pricing_snapshot_id = COALESCE(p_pricing_snapshot_id, pricing_snapshot_id),
      provider_request_id = p_provider_request_id,
      usage_json = p_usage_json,
      status = 'COMMITTED',
      finalized_at = clock_timestamp()
  WHERE reservation_ticket = p_reservation_ticket;

  INSERT INTO provider_cost_ledger (
    reservation_ticket, budget_date, organization_id, operation_id,
    provider, model, entry_type, amount_usd, confidence, pricing_snapshot_id,
    provider_request_id, metadata
  ) VALUES (
    p_reservation_ticket, v_reservation.budget_date,
    v_reservation.organization_id, v_reservation.operation_id,
    v_reservation.provider, v_reservation.model, 'ACTUAL_COST',
    p_actual_amount_usd, p_confidence,
    COALESCE(p_pricing_snapshot_id, v_reservation.pricing_snapshot_id),
    p_provider_request_id,
    jsonb_build_object(
      'usage', p_usage_json,
      'estimated_amount_usd', v_reservation.estimated_amount_usd,
      'actual_overshoot', p_actual_amount_usd > v_reservation.estimated_amount_usd
    )
  );

  RETURN p_reservation_ticket;
END;
$$;

CREATE OR REPLACE FUNCTION provider_cost_release(
  p_reservation_ticket uuid,
  p_reason text
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_reservation provider_cost_reservations%ROWTYPE;
BEGIN
  SELECT * INTO v_reservation
  FROM provider_cost_reservations
  WHERE reservation_ticket = p_reservation_ticket
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'COST_RESERVATION_NOT_FOUND';
  END IF;
  IF v_reservation.status IN ('RELEASED','COMMITTED') THEN
    RETURN p_reservation_ticket;
  END IF;

  PERFORM 1
  FROM provider_cost_daily_usage
  WHERE budget_date = v_reservation.budget_date
  FOR UPDATE;

  UPDATE provider_cost_daily_usage
  SET reserved_usd = GREATEST(0, reserved_usd - v_reservation.estimated_amount_usd),
      updated_at = clock_timestamp()
  WHERE budget_date = v_reservation.budget_date;

  UPDATE provider_cost_reservations
  SET status = 'RELEASED',
      release_reason = left(COALESCE(p_reason, 'released'), 500),
      finalized_at = clock_timestamp()
  WHERE reservation_ticket = p_reservation_ticket;

  INSERT INTO provider_cost_ledger (
    reservation_ticket, budget_date, organization_id, operation_id,
    provider, model, entry_type, amount_usd, confidence, pricing_snapshot_id,
    metadata
  ) VALUES (
    p_reservation_ticket, v_reservation.budget_date,
    v_reservation.organization_id, v_reservation.operation_id,
    v_reservation.provider, v_reservation.model, 'RESERVATION_RELEASE',
    v_reservation.estimated_amount_usd, v_reservation.confidence,
    v_reservation.pricing_snapshot_id,
    jsonb_build_object('reason', left(COALESCE(p_reason, 'released'), 500))
  );

  RETURN p_reservation_ticket;
END;
$$;

CREATE OR REPLACE FUNCTION provider_cost_ledger_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'PROVIDER_COST_LEDGER_APPEND_ONLY';
END;
$$;

DROP TRIGGER IF EXISTS provider_cost_ledger_append_only ON provider_cost_ledger;
CREATE TRIGGER provider_cost_ledger_append_only
BEFORE UPDATE OR DELETE ON provider_cost_ledger
FOR EACH ROW EXECUTE FUNCTION provider_cost_ledger_reject_mutation();

REVOKE UPDATE, DELETE ON provider_cost_ledger FROM PUBLIC;
REVOKE UPDATE, DELETE ON provider_cost_daily_usage FROM PUBLIC;
REVOKE UPDATE, DELETE ON provider_cost_reservations FROM PUBLIC;
REVOKE UPDATE, DELETE ON provider_cost_guard_policy FROM PUBLIC;

COMMIT;
