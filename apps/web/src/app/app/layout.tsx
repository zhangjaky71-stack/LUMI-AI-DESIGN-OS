import { AppShellFrame } from "@/components/app-shell/app-shell-frame";
import { ShellProviders } from "@/components/app-shell/shell-context";
import { requireShellSession } from "@/lib/app-shell/auth-server";
import { getServerPublicFeatureFlags } from "@/lib/app-shell/feature-flags.server";

export const dynamic = "force-dynamic";

export default async function ProductLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const session = await requireShellSession();
  const bootstrap = {
    session,
    public_flags: getServerPublicFeatureFlags(),
  } as const;

  return (
    <ShellProviders bootstrap={bootstrap}>
      <AppShellFrame>{children}</AppShellFrame>
    </ShellProviders>
  );
}
