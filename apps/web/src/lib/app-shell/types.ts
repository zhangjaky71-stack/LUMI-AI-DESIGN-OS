export type OrganizationRole =
  | "OWNER"
  | "ADMIN"
  | "EDITOR"
  | "VIEWER"
  | "BILLING";

export type PlatformAdminRole =
  | "SUPPORT_READ"
  | "SUPPORT_WRITE_LIMITED"
  | "BILLING_ADMIN"
  | "OPS"
  | "MODEL_ADMIN"
  | "SECURITY_AUDITOR"
  | "PRIVACY_ADMIN";

export interface PlatformAdminPrincipal {
  readonly actor_id: string;
  readonly roles: readonly PlatformAdminRole[];
  readonly permissions: readonly string[];
}

export interface ShellUser {
  readonly id: string;
  readonly display_name: string;
  readonly email_hint: string;
}

export interface ShellOrganization {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly role: OrganizationRole;
}

export interface ShellSession {
  readonly session_id: string;
  readonly user: ShellUser;
  readonly organizations: readonly ShellOrganization[];
  readonly active_organization_id: string;
  readonly recent_auth_at?: string;
  readonly platform_admin?: PlatformAdminPrincipal;
}

export interface ProblemDetails {
  readonly type: string;
  readonly title: string;
  readonly status: number;
  readonly code: string;
  readonly detail?: string;
  readonly request_id?: string;
  readonly fields?: Readonly<Record<string, readonly string[]>>;
}

export const PUBLIC_FEATURE_FLAG_NAMES = [
  "projects",
  "brands",
  "assets",
  "team",
  "billing",
  "commandPalette",
] as const;

export type PublicFeatureFlagName =
  (typeof PUBLIC_FEATURE_FLAG_NAMES)[number];
export type PublicFeatureFlags = Readonly<
  Record<PublicFeatureFlagName, boolean>
>;

export interface ShellBootstrap {
  readonly session: ShellSession;
  readonly public_flags: PublicFeatureFlags;
}
