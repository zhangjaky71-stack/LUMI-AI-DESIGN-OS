import { redirect } from "next/navigation";

import { serverApiRequest } from "@/lib/api/server";
import { ApiError } from "@/lib/api/problem";
import { getWebRuntimeConfig } from "@/lib/config/env";
import { AppSession, parseAppSession } from "@/lib/auth/types";

export async function getAppSession(): Promise<AppSession | null> {
  const { sessionPath } = getWebRuntimeConfig();
  try {
    const payload = await serverApiRequest<unknown>(sessionPath, {
      method: "GET",
    });
    return parseAppSession(payload);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export async function requireAppSession(): Promise<AppSession> {
  const session = await getAppSession();
  if (session === null) redirect("/sign-in");
  return session;
}
