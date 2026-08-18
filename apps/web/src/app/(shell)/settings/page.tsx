import Link from "next/link";

import { requireAppSession } from "@/lib/auth/session";

export default async function SettingsShellPage() {
  const session = await requireAppSession();
  const canReadBilling = session.permissions.includes("billing.read");
  return (
    <div className="page-stack">
      <section className="page-heading compact">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Workspace context</h1>
          <p className="page-lead">
            The shell exposes the authenticated tenant context without duplicating backend RBAC.
          </p>
        </div>
      </section>
      <section className="settings-list" aria-label="Current tenant context">
        <div className="settings-row">
          <span>Organization</span>
          <strong>{session.organization.name}</strong>
        </div>
        <div className="settings-row">
          <span>Workspace</span>
          <strong>{session.workspace.name}</strong>
        </div>
        <div className="settings-row">
          <span>Signed in as</span>
          <strong>{session.user.displayName ?? session.user.email ?? session.user.id}</strong>
        </div>
        {canReadBilling ? (
          <div className="settings-row">
            <span>Billing</span>
            <Link href="/settings/billing">Plan, credits and invoices</Link>
          </div>
        ) : null}
      </section>
    </div>
  );
}
