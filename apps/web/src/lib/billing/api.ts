import { serverApiRequest } from "@/lib/api/server";
import { requireAppSession } from "@/lib/auth/session";
import {
  type BillingInvoice,
  type BillingOverview,
  parseBillingInvoices,
  parseBillingOverview,
} from "@/lib/billing/types";

const BILLING_PATH = "/api/v1/billing";

export async function getBillingOverview(): Promise<BillingOverview> {
  const payload = await serverApiRequest<unknown>(`${BILLING_PATH}/overview`, {
    method: "GET",
    headers: await tenantHeaders(),
  });
  return parseBillingOverview(payload);
}

export async function listBillingInvoices(): Promise<readonly BillingInvoice[]> {
  const payload = await serverApiRequest<unknown>(`${BILLING_PATH}/invoices?limit=25`, {
    method: "GET",
    headers: await tenantHeaders(),
  });
  return parseBillingInvoices(payload);
}

async function tenantHeaders(): Promise<Record<string, string>> {
  const session = await requireAppSession();
  return { "X-Organization-ID": session.organization.id };
}
