import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { requireAppSession } from "@/lib/auth/session";

export default async function ShellLayout({ children }: { children: ReactNode }) {
  const session = await requireAppSession();
  return <AppShell session={session}>{children}</AppShell>;
}
