UPDATE cost_ledger
SET confidence='unknown',
    status='reconciled',
    cost_basis='provider_cost',
    source='legacy_migration'
WHERE source='runtime'
  AND entry_type IN ('adjustment','reversal');
