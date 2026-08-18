"use client";

import { useState } from "react";

import { api } from "@/lib/api/client";
import { parseBillingPortal } from "@/lib/billing/types";

export function BillingPortalButton({ organizationId }: { organizationId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openPortal() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const payload = await api.post<unknown>(
        "/api/v1/billing/portal",
        { return_url: `${window.location.origin}/settings/billing` },
        { headers: { "X-Organization-ID": organizationId } },
      );
      const portal = parseBillingPortal(payload);
      window.location.assign(portal.url);
    } catch {
      setError("Billing portal is unavailable right now.");
      setBusy(false);
    }
  }

  return (
    <div>
      <button type="button" onClick={openPortal} disabled={busy}>
        {busy ? "Opening portal…" : "Manage billing"}
      </button>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}
