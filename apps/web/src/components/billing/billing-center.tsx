"use client";

import { useEffect, useMemo, useState } from "react";
import { createBillingGateway } from "@/lib/billing/billing-gateway";
import { creditUsagePercent, entitlementRows, formatMicrousd, planLabel, safeBillingError, safeHttpsBillingUrl } from "@/lib/billing/contracts";
import type { BillingBootstrap, BillingWorkspace, HostedBillingSession } from "@/lib/billing/types";
import styles from "./billing-center.module.css";

export function BillingCenter({ bootstrap }: Readonly<{ bootstrap: BillingBootstrap }>) {
  const gateway = useMemo(() => createBillingGateway(bootstrap), [bootstrap]);
  const [workspace, setWorkspace] = useState<BillingWorkspace | null>(bootstrap.workspace);
  const [session, setSession] = useState<HostedBillingSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (workspace) return;
    const controller = new AbortController();
    gateway.load(controller.signal).then(setWorkspace).catch((value) => setError(safeBillingError(value)));
    return () => controller.abort();
  }, [gateway, workspace]);

  async function act(operation: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const result = await operation();
      if (result && typeof result === "object" && "url" in result) {
        setSession(result as HostedBillingSession);
      }
      setWorkspace(await gateway.load());
    } catch (value) {
      setError(safeBillingError(value));
    } finally {
      setBusy(false);
    }
  }

  if (!workspace) return <div className={styles.shell}><p>{error ?? "Loading billing…"}</p></div>;
  const usage = creditUsagePercent(workspace);
  const hostedSessionUrl = safeHttpsBillingUrl(session?.url ?? null);
  return (
    <section className={styles.shell} aria-label="Billing and usage center">
      <header className={styles.header}>
        <div><span className={styles.eyebrow}>BILLING</span><h1>用量与账单</h1><p>套餐、Credits、订阅和 Hosted Payment 都以服务端 Billing truth 为准。</p></div>
        <span className={styles.provider}>Payment: {workspace.payment_provider}</span>
      </header>
      {error ? <div className={styles.error} role="alert">{error}</div> : null}
      <div className={styles.grid}>
        <article className={styles.card} aria-label="Current billing plan">
          <span className={styles.label}>Current plan</span>
          <h2>{workspace.current_plan ? planLabel(workspace.current_plan) : "No paid plan"}</h2>
          <p>{workspace.current_plan ? `${formatMicrousd(workspace.current_plan.price_microusd, workspace.current_plan.currency)} / ${workspace.current_plan.billing_interval.toLowerCase()}` : "No active subscription"}</p>
          <p className={styles.mono}>Pinned PlanVersion: {workspace.subscription?.plan_version_id ?? "—"}</p>
          <span className={styles.state}>{workspace.subscription?.state ?? "NONE"}</span>
          {workspace.can_manage && workspace.subscription ? <button disabled={busy || workspace.subscription.cancel_at_period_end} onClick={() => void act(() => gateway.cancelSubscription())}>Cancel at period end</button> : null}
        </article>
        <article className={styles.card}>
          <span className={styles.label}>Credits</span><h2>{workspace.credit_balance.toLocaleString()}</h2>
          <p>Immutable Credit Ledger projection</p>
          {usage !== null ? <><div className={styles.progress} aria-label={`Monthly credit usage ${usage}%`}><span style={{ width: `${usage}%` }} /></div><small>{usage}% of included monthly credits used</small></> : null}
        </article>
      </div>
      <div className={styles.columns}>
        <article className={styles.card}>
          <h2>Entitlements</h2>
          <p>功能代码查询 Entitlement Service，不按套餐名硬编码。</p>
          <div className={styles.chips}>{entitlementRows(workspace).map(([key, value]) => <span key={key}>{key}: {value}</span>)}</div>
        </article>
        <article className={styles.card}>
          <h2>Payment portal</h2><p>LUMI 不收集银行卡敏感字段。支付方式由 Hosted Checkout / Portal 处理。</p>
          {workspace.can_manage ? <button disabled={busy} onClick={() => void act(() => gateway.createPortal())}>Create hosted portal session</button> : <p>Billing manager permission required.</p>}
          {hostedSessionUrl ? <a className={styles.hosted} href={hostedSessionUrl} rel="noreferrer">Open hosted {hostedSessionUrl.includes("checkout") ? "checkout" : "portal"} →</a> : null}
        </article>
      </div>
      <article className={styles.card}><h2>Available plan versions</h2><div className={styles.planGrid}>{workspace.plans.map((plan) => <div className={styles.plan} key={plan.plan_version_id}><strong>{planLabel(plan)}</strong><span>{formatMicrousd(plan.price_microusd, plan.currency)} / {plan.billing_interval.toLowerCase()}</span><span>{plan.monthly_credit_grant.toLocaleString()} credits / month</span>{workspace.can_manage && plan.plan_version_id !== workspace.subscription?.plan_version_id ? <button disabled={busy} onClick={() => void act(() => gateway.createCheckout(plan.plan_version_id))}>Create hosted checkout</button> : <span className={styles.current}>{plan.plan_version_id === workspace.subscription?.plan_version_id ? "Current exact version" : ""}</span>}</div>)}</div></article>
      <div className={styles.columns}>
        <article className={styles.card}><h2>Credit ledger</h2>{workspace.credit_entries.map((entry) => <div className={styles.row} key={entry.entry_id}><span>{entry.entry_type} · {entry.source_type}</span><strong>{entry.delta_credits > 0 ? "+" : ""}{entry.delta_credits}</strong></div>)}</article>
        <article className={styles.card}><h2>Invoices</h2>{workspace.invoices.length ? workspace.invoices.map((invoice) => { const invoiceUrl = safeHttpsBillingUrl(invoice.hosted_invoice_url); return <div className={styles.row} key={invoice.invoice_id}><span>{invoice.status} · {invoice.provider_invoice_ref} · {invoice.plan_version_id}</span><span>{formatMicrousd(invoice.amount_due_microusd, invoice.currency)} {invoiceUrl ? <a href={invoiceUrl} rel="noreferrer">Invoice ↗</a> : null}</span></div>; }) : <p>No invoices yet.</p>}</article>
      </div>
      <footer className={styles.truth}><strong>Truth boundary</strong><span>Provider Cost Ledger ≠ Customer Usage ≠ Customer Billing ≠ Credits/Entitlements.</span><span>Provider cost reconciliation: {workspace.provider_cost_reconciliation_available ? "available" : "integration pending (NODE-27 runtime)"}.</span></footer>
    </section>
  );
}
