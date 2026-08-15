import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { assertShellSession } from "./auth-contract";
import type { ShellSession } from "./types";

export interface ShellSessionAdapter {
  getSession(): Promise<ShellSession | null>;
}

const E2E_SESSION: ShellSession = {
  session_id: "e2e-shell-session",
  user: {
    id: "user-e2e",
    display_name: "Design Operator",
    email_hint: "d•••@example.test",
  },
  organizations: [
    { id: "org-lumi", name: "LUMI Studio", slug: "lumi-studio", role: "OWNER" },
    { id: "org-northstar", name: "Northstar Lab", slug: "northstar-lab", role: "EDITOR" },
  ],
  active_organization_id: "org-lumi",
  recent_auth_at: "2026-08-15T00:00:00.000Z",
};

class DeferredNode16SessionAdapter implements ShellSessionAdapter {
  async getSession(): Promise<ShellSession | null> {
    if (process.env.LUMI_SHELL_E2E_AUTH !== "1") return null;
    const cookieStore = await cookies();
    if (cookieStore.get("lumi_e2e_anon")?.value === "1") return null;
    return E2E_SESSION;
  }
}

const defaultAdapter: ShellSessionAdapter = new DeferredNode16SessionAdapter();

export async function getShellSession(adapter: ShellSessionAdapter = defaultAdapter): Promise<ShellSession | null> {
  const session = await adapter.getSession();
  return session ? assertShellSession(session) : null;
}

export async function requireShellSession(adapter: ShellSessionAdapter = defaultAdapter): Promise<ShellSession> {
  const session = await getShellSession(adapter);
  if (!session) redirect("/login?reason=session-required");
  return session;
}
