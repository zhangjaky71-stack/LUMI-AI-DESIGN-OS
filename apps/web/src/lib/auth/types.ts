export type SessionUser = {
  id: string;
  email?: string | null;
  displayName?: string | null;
};

export type SessionOrganization = {
  id: string;
  name: string;
};

export type SessionWorkspace = {
  id: string;
  name: string;
};

export type AppSession = {
  user: SessionUser;
  organization: SessionOrganization;
  workspace: SessionWorkspace;
  permissions: readonly string[];
  expiresAt?: string | null;
};

export function parseAppSession(value: unknown): AppSession {
  if (!isRecord(value)) throw new Error("SESSION_PAYLOAD_INVALID");
  const user = requireRecord(value.user, "SESSION_USER_INVALID");
  const organization = requireRecord(
    value.organization,
    "SESSION_ORGANIZATION_INVALID",
  );
  const workspace = requireRecord(value.workspace, "SESSION_WORKSPACE_INVALID");
  const permissions = value.permissions ?? [];
  if (!Array.isArray(permissions) || !permissions.every((item) => typeof item === "string")) {
    throw new Error("SESSION_PERMISSIONS_INVALID");
  }

  return {
    user: {
      id: requireString(user.id, "SESSION_USER_ID_REQUIRED"),
      email: optionalString(user.email, "SESSION_USER_EMAIL_INVALID"),
      displayName: optionalString(
        user.displayName ?? user.display_name,
        "SESSION_USER_DISPLAY_NAME_INVALID",
      ),
    },
    organization: {
      id: requireString(organization.id, "SESSION_ORGANIZATION_ID_REQUIRED"),
      name: requireString(organization.name, "SESSION_ORGANIZATION_NAME_REQUIRED"),
    },
    workspace: {
      id: requireString(workspace.id, "SESSION_WORKSPACE_ID_REQUIRED"),
      name: requireString(workspace.name, "SESSION_WORKSPACE_NAME_REQUIRED"),
    },
    permissions: [...permissions],
    expiresAt: optionalString(
      value.expiresAt ?? value.expires_at,
      "SESSION_EXPIRY_INVALID",
    ),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, code: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(code);
  return value;
}

function requireString(value: unknown, code: string): string {
  if (typeof value !== "string" || value.trim().length === 0) throw new Error(code);
  return value;
}

function optionalString(value: unknown, code: string): string | null | undefined {
  if (value === undefined || value === null) return value;
  if (typeof value !== "string") throw new Error(code);
  return value;
}
