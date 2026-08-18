import Link from "next/link";
import type { ReactNode } from "react";

import type { AppSession } from "@/lib/auth/types";
import { AppNav } from "@/components/shell/app-nav";
import { TopBar } from "@/components/shell/top-bar";

export function AppShell({
  session,
  children,
}: {
  session: AppSession;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <Link href="/" className="brand-link" aria-label="LUMI home">
            <span className="brand-mark" aria-hidden="true">L</span>
            <span>
              <strong>LUMI</strong>
              <small>Design OS</small>
            </span>
          </Link>
        </div>
        <AppNav />
        <div className="sidebar-footnote">
          <span>Workspace</span>
          <strong>{session.workspace.name}</strong>
        </div>
      </aside>
      <div className="shell-main">
        <TopBar session={session} />
        <main id="main-content" className="page-canvas" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
