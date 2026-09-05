import { BillingCenter } from "@/components/billing/billing-center";
import { getBillingBootstrap } from "@/lib/billing/billing-server";

export const dynamic = "force-dynamic";

export default function BillingPage() {
  return <BillingCenter bootstrap={getBillingBootstrap()} />;
}
