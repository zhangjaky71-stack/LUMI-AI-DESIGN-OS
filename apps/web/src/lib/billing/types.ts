export type BillingSubscriptionState =
  | "TRIALING" | "ACTIVE" | "PAST_DUE" | "CANCEL_AT_PERIOD_END" | "CANCELLED" | "INCOMPLETE";
export type CreditEntryType = "GRANT" | "CONSUME" | "REFUND" | "EXPIRE" | "ADJUSTMENT" | "REVERSAL";

export interface BillingPlanVersion {
  readonly plan_id: string;
  readonly plan_version_id: string;
  readonly version: number;
  readonly name: string;
  readonly currency: string;
  readonly price_microusd: number;
  readonly billing_interval: "MONTH" | "YEAR";
  readonly monthly_credit_grant: number;
  readonly entitlements: Readonly<Record<string, number | boolean | string>>;
  readonly status: "ACTIVE" | "ARCHIVED";
}

export interface BillingSubscription {
  readonly subscription_id: string;
  readonly organization_id: string;
  readonly plan_version_id: string;
  readonly payment_provider: string;
  readonly provider_subscription_ref: string;
  readonly state: BillingSubscriptionState;
  readonly current_period_start: string | null;
  readonly current_period_end: string | null;
  readonly cancel_at_period_end: boolean;
}

export interface CreditLedgerEntry {
  readonly entry_id: string;
  readonly organization_id: string;
  readonly entry_type: CreditEntryType;
  readonly delta_credits: number;
  readonly source_type: string;
  readonly source_id: string;
  readonly pricing_policy_version: number | null;
  readonly idempotency_key: string;
  readonly created_at: string;
}

export interface BillingInvoice {
  readonly invoice_id: string;
  readonly organization_id: string;
  readonly provider: string;
  readonly provider_invoice_ref: string;
  readonly plan_version_id: string;
  readonly status: "PAID" | "OPEN" | "FAILED" | "VOID";
  readonly amount_due_microusd: number;
  readonly currency: string;
  readonly hosted_invoice_url: string | null;
  readonly created_at: string;
}

export interface BillingWorkspace {
  readonly organization_id: string;
  readonly current_plan: BillingPlanVersion | null;
  readonly subscription: BillingSubscription | null;
  readonly plans: readonly BillingPlanVersion[];
  readonly credit_balance: number;
  readonly credit_entries: readonly CreditLedgerEntry[];
  readonly invoices: readonly BillingInvoice[];
  readonly entitlements: Readonly<Record<string, number | boolean | string>>;
  readonly can_manage: boolean;
  readonly payment_provider: string;
  readonly provider_cost_reconciliation_available: boolean;
}

export interface HostedBillingSession {
  readonly provider: string;
  readonly session_ref: string;
  readonly url: string;
}

export interface BillingBootstrap {
  readonly mode: "HTTP" | "DETERMINISTIC";
  readonly workspace: BillingWorkspace | null;
}
