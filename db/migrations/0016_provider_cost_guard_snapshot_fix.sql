BEGIN;

-- The initial provider-cost migration snapshots the active cap into the UTC-day
-- usage row. This replacement makes that snapshot authoritative for every later
-- reservation on the same day, so a policy edit cannot silently raise or lower
-- an already-open day's spend boundary.
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
  v_policy_cap numeric(20,8);
  v_day_cap numeric(20,8);
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
    INTO v_policy_cap, v_enabled, v_fail_closed
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
    (v_day, 'USD', v_policy_cap, 0, 0)
  ON CONFLICT (budget_date) DO NOTHING;

  -- The day row is both the serialization point and the authoritative cap
  -- snapshot. Concurrent reservations for the same UTC day cannot pass this
  -- lock simultaneously, and later policy edits do not mutate v_day_cap.
  SELECT cap_usd, reserved_usd, committed_usd
    INTO v_day_cap, v_reserved, v_committed
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

  IF v_committed + v_reserved + p_estimated_amount_usd > v_day_cap THEN
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

COMMIT;
