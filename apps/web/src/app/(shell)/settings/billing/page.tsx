import Link from "next/link";

import { BillingPortalButton } from "@/components/billing/billing-portal-button";
import { requireAppSession } from "@/lib/auth/session";
import { getBillingOverview, listBillingInvoices } from "@/lib/billing/api";

export default async function BillingSettingsPage() {
  const session = await requireAppSession();
  const canRead = session.permissions.includes("billing.read");
  const canManage = session.permissions.includes("billing.manage");

  if (!canRead) {
    return (
      <div className="page-stack">
        <section className="page-heading compact">
          <div>
            <p className="eyebrow">Settings · Billing</p>
            <h1>Billing access required</h1>
            <p className="page-lead">
              Your organization role does not include billing.read.
            </p>
          </div>
        </section>
        <Link href="/settings">Back to settings</Link>
      </div>
    );
  }

  try {
    const [overview, invoices] = await Promise.all([
      getBillingOverview(),
      listBillingInvoices(),
    ]);
    return (
      <div className="page-stack">
        <section className="page-heading compact">
          <div>
            <p className="eyebrow">Settings · Billing</p>
            <h1>{overview.plan?.name ?? "No active plan"}</h1>
            <p className="page-lead">
              Credits, subscription state, entitlements and provider-hosted invoices.
            </p>
          </div>
          {canManage ? (
            <BillingPortalButton organizationId={session.organization.id} />
          ) : null}
        </section>

        <section className="settings-list" aria-label="Billing overview">
          <div className="settings-row">
            <span>Subscription</span>
            <strong>{overview.subscription?.state ?? "NONE"}</strong>
          </div>
          <div className="settings-row">
            <span>Credits</span>
            <strong>{overview.credits.balance}</strong>
          </div>
          <div className="settings-row">
            <span>Included credits</span>
            <strong>{overview.plan?.includedCredits ?? "0"}</strong>
          </div>
          <div className="settings-row">
            <span>Paid features</span>
            <strong>
              {overview.entitlements.canConsumePaidFeatures ? "Available" : "Blocked"}
            </strong>
          </div>
          <div className="settings-row">
            <span>Postpaid</span>
            <strong>{overview.credits.allowPostpaid ? "Enabled" : "Disabled"}</strong>
          </div>
        </section>

        <section className="page-heading compact">
          <div>
            <p className="eyebrow">Invoices</p>
            <h2>Provider-hosted billing history</h2>
          </div>
        </section>
        <section className="settings-list" aria-label="Invoices">
          {invoices.length === 0 ? (
            <div className="settings-row">
              <span>No invoices yet</span>
              <strong>—</strong>
            </div>
          ) : (
            invoices.map((invoice) => (
              <div className="settings-row" key={invoice.providerInvoiceRef}>
                <span>
                  {invoice.currency} {invoice.amountDue} · {invoice.status}
                </span>
                {invoice.hostedInvoiceUrl ? (
                  <a href={invoice.hostedInvoiceUrl} target="_blank" rel="noreferrer">
                    View invoice
                  </a>
                ) : (
                  <strong>{invoice.providerInvoiceRef}</strong>
                )}
              </div>
            ))
          )}
        </section>
        <Link href="/settings">Back to settings</Link>
      </div>
    );
  } catch {
    return (
      <div className="page-stack">
        <section className="page-heading compact">
          <div>
            <p className="eyebrow">Settings · Billing</p>
            <h1>Billing service unavailable</h1>
            <p className="page-lead">
              The Billing contracts are installed, but this deployment has not composed the
              production billing service yet.
            </p>
          </div>
        </section>
        <Link href="/settings">Back to settings</Link>
      </div>
    );
  }
}
