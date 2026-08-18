export type BillingOverview = {
  plan: {
    id: string;
    key: string;
    name: string;
    version: number;
    currency: string;
    monthlyPrice: string;
    includedCredits: string;
  } | null;
  subscription: {
    id: string;
    state: string;
    currentPeriodEnd: string | null;
    cancelAtPeriodEnd: boolean;
  } | null;
  credits: {
    balance: string;
    allowPostpaid: boolean;
  };
  entitlements: {
    state: string | null;
    planVersionId: string | null;
    entitlements: Readonly<Record<string, unknown>>;
    creditsBalance: string;
    canConsumePaidFeatures: boolean;
  };
};

export type BillingInvoice = {
  providerInvoiceRef: string;
  status: string;
  amountDue: string;
  currency: string;
  hostedInvoiceUrl: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  createdAt: string;
};

export type BillingPortal = {
  provider: string;
  url: string;
};

export function parseBillingOverview(value: unknown): BillingOverview {
  const root = record(value, "BILLING_OVERVIEW_INVALID");
  const credits = record(root.credits, "BILLING_CREDITS_INVALID");
  const entitlements = record(root.entitlements, "BILLING_ENTITLEMENTS_INVALID");
  return {
    plan: root.plan === null ? null : parsePlan(root.plan),
    subscription:
      root.subscription === null ? null : parseSubscription(root.subscription),
    credits: {
      balance: decimalString(credits.balance, "BILLING_BALANCE_INVALID"),
      allowPostpaid: boolean(credits.allow_postpaid, "BILLING_POSTPAID_INVALID"),
    },
    entitlements: {
      state: nullableString(entitlements.state, "BILLING_ENTITLEMENT_STATE_INVALID"),
      planVersionId: nullableString(
        entitlements.plan_version_id,
        "BILLING_ENTITLEMENT_PLAN_VERSION_INVALID",
      ),
      entitlements: record(
        entitlements.entitlements,
        "BILLING_ENTITLEMENT_PAYLOAD_INVALID",
      ),
      creditsBalance: decimalString(
        entitlements.credits_balance,
        "BILLING_ENTITLEMENT_BALANCE_INVALID",
      ),
      canConsumePaidFeatures: boolean(
        entitlements.can_consume_paid_features,
        "BILLING_ENTITLEMENT_CONSUME_INVALID",
      ),
    },
  };
}

export function parseBillingInvoices(value: unknown): readonly BillingInvoice[] {
  if (!Array.isArray(value)) throw new Error("BILLING_INVOICES_INVALID");
  return value.map((item) => {
    const row = record(item, "BILLING_INVOICE_INVALID");
    return {
      providerInvoiceRef: string(row.provider_invoice_ref, "BILLING_INVOICE_REF_INVALID"),
      status: string(row.status, "BILLING_INVOICE_STATUS_INVALID"),
      amountDue: decimalString(row.amount_due, "BILLING_INVOICE_AMOUNT_INVALID"),
      currency: string(row.currency, "BILLING_INVOICE_CURRENCY_INVALID"),
      hostedInvoiceUrl: nullableString(
        row.hosted_invoice_url,
        "BILLING_INVOICE_URL_INVALID",
      ),
      periodStart: nullableString(row.period_start, "BILLING_INVOICE_PERIOD_INVALID"),
      periodEnd: nullableString(row.period_end, "BILLING_INVOICE_PERIOD_INVALID"),
      createdAt: string(row.created_at, "BILLING_INVOICE_CREATED_INVALID"),
    };
  });
}

export function parseBillingPortal(value: unknown): BillingPortal {
  const row = record(value, "BILLING_PORTAL_INVALID");
  const url = string(row.url, "BILLING_PORTAL_URL_INVALID");
  if (!url.startsWith("https://") && !url.startsWith("http://localhost")) {
    throw new Error("BILLING_PORTAL_URL_UNSAFE");
  }
  return {
    provider: string(row.provider, "BILLING_PORTAL_PROVIDER_INVALID"),
    url,
  };
}

function parsePlan(value: unknown): NonNullable<BillingOverview["plan"]> {
  const row = record(value, "BILLING_PLAN_INVALID");
  return {
    id: string(row.id, "BILLING_PLAN_ID_INVALID"),
    key: string(row.key, "BILLING_PLAN_KEY_INVALID"),
    name: string(row.name, "BILLING_PLAN_NAME_INVALID"),
    version: integer(row.version, "BILLING_PLAN_VERSION_INVALID"),
    currency: string(row.currency, "BILLING_PLAN_CURRENCY_INVALID"),
    monthlyPrice: decimalString(row.monthly_price, "BILLING_PLAN_PRICE_INVALID"),
    includedCredits: decimalString(
      row.included_credits,
      "BILLING_PLAN_CREDITS_INVALID",
    ),
  };
}

function parseSubscription(
  value: unknown,
): NonNullable<BillingOverview["subscription"]> {
  const row = record(value, "BILLING_SUBSCRIPTION_INVALID");
  return {
    id: string(row.id, "BILLING_SUBSCRIPTION_ID_INVALID"),
    state: string(row.state, "BILLING_SUBSCRIPTION_STATE_INVALID"),
    currentPeriodEnd: nullableString(
      row.current_period_end,
      "BILLING_SUBSCRIPTION_PERIOD_INVALID",
    ),
    cancelAtPeriodEnd: boolean(
      row.cancel_at_period_end,
      "BILLING_SUBSCRIPTION_CANCEL_INVALID",
    ),
  };
}

function record(value: unknown, code: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(code);
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, code: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(code);
  return value;
}

function nullableString(value: unknown, code: string): string | null {
  if (value === null) return null;
  return string(value, code);
}

function boolean(value: unknown, code: string): boolean {
  if (typeof value !== "boolean") throw new Error(code);
  return value;
}

function integer(value: unknown, code: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
    throw new Error(code);
  }
  return value;
}

function decimalString(value: unknown, code: string): string {
  if (typeof value !== "string" && typeof value !== "number") throw new Error(code);
  const normalized = String(value);
  if (!/^-?\d+(?:\.\d+)?$/.test(normalized)) throw new Error(code);
  return normalized;
}
