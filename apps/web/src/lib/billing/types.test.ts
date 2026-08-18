import { describe, expect, it } from "vitest";

import {
  parseBillingInvoices,
  parseBillingOverview,
  parseBillingPortal,
} from "@/lib/billing/types";

describe("NODE-63 billing parsers", () => {
  it("parses the minimal billing overview without leaking provider internals", () => {
    const overview = parseBillingOverview({
      plan: {
        id: "plan-version-1",
        key: "studio",
        name: "Studio",
        version: 3,
        currency: "USD",
        monthly_price: "29.00",
        included_credits: "1000",
      },
      subscription: {
        id: "subscription-1",
        state: "ACTIVE",
        current_period_end: "2026-09-18T00:00:00Z",
        cancel_at_period_end: false,
      },
      credits: { balance: "42.5", allow_postpaid: false },
      entitlements: {
        state: "ACTIVE",
        plan_version_id: "plan-version-1",
        entitlements: { "video.enabled": true },
        credits_balance: "42.5",
        can_consume_paid_features: true,
      },
    });

    expect(overview.plan?.name).toBe("Studio");
    expect(overview.credits.balance).toBe("42.5");
    expect(overview.entitlements.entitlements["video.enabled"]).toBe(true);
  });

  it("fails closed on malformed credit balances", () => {
    expect(() =>
      parseBillingOverview({
        plan: null,
        subscription: null,
        credits: { balance: "NaN", allow_postpaid: false },
        entitlements: {
          state: null,
          plan_version_id: null,
          entitlements: {},
          credits_balance: "0",
          can_consume_paid_features: false,
        },
      }),
    ).toThrow("BILLING_BALANCE_INVALID");
  });

  it("only accepts hosted https or localhost portal URLs", () => {
    expect(parseBillingPortal({ provider: "mock", url: "https://payments.example/portal" }).url)
      .toBe("https://payments.example/portal");
    expect(() => parseBillingPortal({ provider: "mock", url: "javascript:alert(1)" }))
      .toThrow("BILLING_PORTAL_URL_UNSAFE");
  });

  it("parses provider-hosted invoice references", () => {
    const invoices = parseBillingInvoices([
      {
        provider_invoice_ref: "inv_1",
        status: "paid",
        amount_due: "29.00",
        currency: "USD",
        hosted_invoice_url: "https://payments.example/invoice/1",
        period_start: null,
        period_end: null,
        created_at: "2026-08-18T00:00:00Z",
      },
    ]);
    expect(invoices).toHaveLength(1);
    expect(invoices[0]?.providerInvoiceRef).toBe("inv_1");
  });
});
