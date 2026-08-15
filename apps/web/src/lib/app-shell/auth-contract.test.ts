import { describe, expect, it } from "vitest";
import { assertShellSession, hasRecentAuthentication } from "./auth-contract";

const base = {
  session_id: "s1",
  user: {
    id: "u1",
    display_name: "User",
    email_hint: "u•••@example.test",
  },
  organizations: [
    { id: "org-1", name: "One", slug: "one", role: "OWNER" as const },
  ],
  active_organization_id: "org-1",
  recent_auth_at: "2026-08-15T00:00:00.000Z",
};

describe("shell session contract", () => {
  it("accepts an active organization backed by membership", () => {
    expect(assertShellSession(base).active_organization_id).toBe("org-1");
  });

  it("rejects cross-organization active ids", () => {
    expect(() =>
      assertShellSession({ ...base, active_organization_id: "org-other" }),
    ).toThrow("SHELL_SESSION_ACTIVE_ORGANIZATION_INVALID");
  });

  it("validates a platform admin principal separately from tenant roles", () => {
    const platform = assertShellSession({
      ...base,
      platform_admin: {
        actor_id: "platform-1",
        roles: ["OPS" as const],
        permissions: ["admin.provider.read"],
      },
    });
    expect(platform.platform_admin?.actor_id).toBe("platform-1");
    expect(platform.organizations[0]?.role).toBe("OWNER");
    expect(() =>
      assertShellSession({
        ...base,
        platform_admin: {
          actor_id: "platform-1",
          roles: [],
          permissions: [],
        },
      }),
    ).toThrow("SHELL_PLATFORM_ADMIN_INVALID");
  });

  it("exposes a bounded recent-auth hint without inventing authorization", () => {
    const now = Date.parse("2026-08-15T00:04:00.000Z");
    expect(hasRecentAuthentication(base, 5 * 60_000, now)).toBe(true);
    expect(hasRecentAuthentication(base, 3 * 60_000, now)).toBe(false);
  });
});
