import { redirect } from "next/navigation";

import { serverApiRequest } from "@/lib/api/server";
import { getWebRuntimeConfig } from "@/lib/config/env";
import type { AppSession } from "@/lib/auth/types";

export function TopBar({ session }: { session: AppSession }) {
  async function signOut() {
    "use server";
    const { signOutPath } = getWebRuntimeConfig();
    try {
      await serverApiRequest<unknown>(signOutPath, { method: "POST" });
    } finally {
      redirect("/sign-in");
    }
  }

  const userLabel =
    session.user.displayName ?? session.user.email ?? "Account";
  const initials = userLabel
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "U";

  return (
    <header className="top-bar">
      <div className="tenant-context" aria-label="Current workspace">
        <span className="tenant-org">{session.organization.name}</span>
        <span className="tenant-divider" aria-hidden="true">/</span>
        <strong>{session.workspace.name}</strong>
      </div>
      <div className="account-menu">
        <span className="account-avatar" aria-hidden="true">{initials}</span>
        <span className="account-name">{userLabel}</span>
        <form action={signOut}>
          <button className="text-button" type="submit">Sign out</button>
        </form>
      </div>
    </header>
  );
}
