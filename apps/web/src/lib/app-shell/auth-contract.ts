import type { ShellSession } from "./types";

export function assertShellSession(session: ShellSession): ShellSession {
  if (!session.session_id || !session.user.id) {
    throw new Error("SHELL_SESSION_INVALID");
  }
  if (!session.organizations.length) {
    throw new Error("SHELL_SESSION_ORGANIZATION_REQUIRED");
  }
  if (
    !session.organizations.some(
      (organization) => organization.id === session.active_organization_id,
    )
  ) {
    throw new Error("SHELL_SESSION_ACTIVE_ORGANIZATION_INVALID");
  }
  return session;
}

export function hasRecentAuthentication(
  session: ShellSession,
  maxAgeMs: number,
  nowMs = Date.now(),
): boolean {
  if (!Number.isFinite(maxAgeMs) || maxAgeMs < 0) {
    throw new Error("RECENT_AUTH_MAX_AGE_INVALID");
  }
  if (!session.recent_auth_at) return false;

  const authenticatedAt = Date.parse(session.recent_auth_at);
  if (!Number.isFinite(authenticatedAt)) return false;
  const age = nowMs - authenticatedAt;
  return age >= 0 && age <= maxAgeMs;
}
