DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM usage_ledger)
     OR EXISTS (SELECT 1 FROM cost_reservations)
     OR EXISTS (SELECT 1 FROM quota_limits)
     OR EXISTS (SELECT 1 FROM quota_leases)
     OR EXISTS (SELECT 1 FROM cost_budget_limits)
     OR EXISTS (SELECT 1 FROM cost_budget_change_audit)
     OR EXISTS (
       SELECT 1 FROM cost_ledger
       WHERE source <> 'legacy_migration'
     ) THEN
    RAISE EXCEPTION
      'NODE-27 downgrade refused: new cost/usage/budget/quota facts would be lost';
  END IF;
END;
$$;
