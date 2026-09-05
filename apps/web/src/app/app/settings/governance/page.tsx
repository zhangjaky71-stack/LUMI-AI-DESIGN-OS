import { GovernanceCenter } from "@/components/governance/governance-center";
import { requireShellSession } from "@/lib/app-shell/auth-server";
import { getGovernanceBootstrap } from "@/lib/governance/governance-server";

export const dynamic = "force-dynamic";

export default async function GovernancePage() {
  const session = await requireShellSession();
  return <GovernanceCenter bootstrap={getGovernanceBootstrap(session)} />;
}
