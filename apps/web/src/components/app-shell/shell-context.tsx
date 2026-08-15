"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LumiApiClient } from "@/lib/app-shell/api-client";
import { OrgScopedQueryCache } from "@/lib/app-shell/query-cache";
import { SafeTelemetry } from "@/lib/app-shell/telemetry";
import type { PublicFeatureFlags, ShellBootstrap, ShellOrganization, ShellSession } from "@/lib/app-shell/types";

interface ShellContextValue {
  readonly session: ShellSession;
  readonly activeOrganization: ShellOrganization;
  readonly flags: PublicFeatureFlags;
  readonly api: LumiApiClient;
  readonly queryCache: OrgScopedQueryCache;
  readonly switchOrganization: (organizationId: string) => void;
  readonly commandPaletteOpen: boolean;
  readonly setCommandPaletteOpen: (open: boolean) => void;
}

const ShellContext = createContext<ShellContextValue | null>(null);

export function ShellProviders({ bootstrap, children }: Readonly<{ bootstrap: ShellBootstrap; children: React.ReactNode }>) {
  const [session, setSession] = useState(bootstrap.session);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const telemetryRef = useRef(new SafeTelemetry());
  const queryCacheRef = useRef<OrgScopedQueryCache | null>(null);
  if (queryCacheRef.current === null) queryCacheRef.current = new OrgScopedQueryCache(session.active_organization_id);
  const queryCache = queryCacheRef.current;

  const api = useMemo(
    () => new LumiApiClient({ context: () => ({ organization_id: session.active_organization_id }) }),
    [session.active_organization_id],
  );

  useEffect(() => {
    telemetryRef.current.emit("page.viewed", { path: pathname });
  }, [pathname]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandPaletteOpen(true);
      }
      if (event.key === "Escape") setCommandPaletteOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const activeOrganization = session.organizations.find((organization) => organization.id === session.active_organization_id);
  if (!activeOrganization) throw new Error("SHELL_ACTIVE_ORGANIZATION_MISSING");

  const switchOrganization = (organizationId: string) => {
    if (organizationId === session.active_organization_id) return;
    const next = session.organizations.find((organization) => organization.id === organizationId);
    if (!next) return;
    queryCache.switchOrganization(organizationId);
    setSession((current) => ({ ...current, active_organization_id: organizationId }));
    telemetryRef.current.emit("organization.switched", { organization_id: organizationId });
    router.push("/app/projects");
  };

  return (
    <ShellContext.Provider
      value={{
        session,
        activeOrganization,
        flags: bootstrap.public_flags,
        api,
        queryCache,
        switchOrganization,
        commandPaletteOpen,
        setCommandPaletteOpen,
      }}
    >
      {children}
    </ShellContext.Provider>
  );
}

export function useShell(): ShellContextValue {
  const value = useContext(ShellContext);
  if (!value) throw new Error("SHELL_CONTEXT_REQUIRED");
  return value;
}
