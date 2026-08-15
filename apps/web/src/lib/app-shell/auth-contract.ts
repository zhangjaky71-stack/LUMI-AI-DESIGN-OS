import type { ShellSession } from "./types";

export function assertShellSession(session: ShellSession): ShellSession {
  if (!session.session_id || !session.user.id) throw new Error("SHELL_SESSION_INVALID");
  if (!session.organizations.length) throw new Error("SHELL_SESSION_ORGANIZATION_REQUIRED");
  if (!session.organizations.some((organization) => organization.id === session.active_organization_id)) {
    throw new Error("SHELL_SESSION_ACTIVE_ORGANIZATION_INVALID");
  }
  return session;
}
