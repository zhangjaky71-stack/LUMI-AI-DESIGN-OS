DROP TRIGGER IF EXISTS trg_billing_plan_version_material_immutable ON billing_plan_versions;

-- statement-breakpoint

DROP FUNCTION IF EXISTS billing_guard_plan_version_material_update();

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_billing_credit_ledger_immutable ON billing_credit_ledger;

-- statement-breakpoint

DROP FUNCTION IF EXISTS billing_reject_credit_ledger_mutation();

-- statement-breakpoint

DROP TABLE IF EXISTS billing_payment_events;

-- statement-breakpoint

DROP TABLE IF EXISTS billing_invoice_refs;

-- statement-breakpoint

DROP TABLE IF EXISTS billing_credit_ledger;

-- statement-breakpoint

DROP TABLE IF EXISTS billing_credit_wallets;

-- statement-breakpoint

DROP TABLE IF EXISTS billing_subscriptions;

-- statement-breakpoint

DROP TABLE IF EXISTS billing_accounts;

-- statement-breakpoint

DROP TABLE IF EXISTS billing_plan_versions;

-- statement-breakpoint

DROP TABLE IF EXISTS billing_plans;
