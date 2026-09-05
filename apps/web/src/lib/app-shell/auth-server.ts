import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { assertShellSession } from "./auth-contract";
import type { ShellSession } from "./types";

export interface ShellSessionAdapter {
  getSession(): Promise<ShellSession | null>;
}

function e2eSession(): ShellSession {
  const platformAdmin =
    process.env.LUMI_ADMIN_E2E === "1"
      ? {
          actor_id: "platform-admin-e2e",
          roles: [
            "OPS",
            "BILLING_ADMIN",
            "MODEL_ADMIN",
            "SECURITY_AUDITOR",
            "PRIVACY_ADMIN",
          ] as const,
          permissions: [
            "admin.user.read",
            "admin.user.manage_limited",
            "admin.billing.read",
            "admin.billing.adjust",
            "admin.provider.read",
            "admin.provider.manage",
            "admin.queue.read",
            "admin.queue.requeue",
            "admin.agent_registry.manage",
            "admin.skill_registry.manage",
            "admin.audit.read",
            "admin.privacy.execute",
          ] as const,
        }
      : undefined;
  return {
    session_id: "e2e-shell-session",
    user: {
      id: "user-e2e",
      display_name: "Design Operator",
      email_hint: "d•••@example.test",
    },
    organizations: [
      {
        id: "org-lumi",
        name: "LUMI Studio",
        slug: "lumi-studio",
        role: "OWNER",
      },
      {
        id: "org-northstar",
        name: "Northstar Lab",
        slug: "northstar-lab",
        role: "EDITOR",
      },
    ],
    active_organization_id: "org-lumi",
    recent_auth_at: "2026-08-15T00:00:00.000Z",
    ...(platformAdmin ? { platform_admin: platformAdmin } : {}),
  };
}

class DeferredNode16SessionAdapter implements ShellSessionAdapter {
  async getSession(): Promise<ShellSession | null> {
    if (process.env.NODE_ENV === "production") return null;
    if (process.env.LUMI_SHELL_E2E_AUTH !== "1") return null;

    const cookieStore = await cookies();
    if (cookieStore.get("lumi_e2e_anon")?.value === "1") return null;
    return e2eSession();
  }
}

const defaultAdapter: ShellSessionAdapter = new DeferredNode16SessionAdapter();

export async function getShellSession(
  adapter: ShellSessionAdapter = defaultAdapter,
): Promise<ShellSession | null> {
  const session = await adapter.getSession();
  return session ? assertShellSession(session) : null;
}

export async function requireShellSession(
  adapter: ShellSessionAdapter = defaultAdapter,
): Promise<ShellSession> {
  const session = await getShellSession(adapter);
  if (!session) redirect("/login?reason=session-required");
  return session;
}
