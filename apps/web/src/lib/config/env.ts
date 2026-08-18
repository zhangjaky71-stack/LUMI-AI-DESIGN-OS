const DEFAULT_API_ORIGIN = "http://localhost:8000";
const DEFAULT_SESSION_PATH = "/api/v1/auth/session";
const DEFAULT_SIGN_IN_PATH = "/api/v1/auth/login";
const DEFAULT_SIGN_OUT_PATH = "/api/v1/auth/logout";

export type WebRuntimeConfig = {
  apiOrigin: string;
  sessionPath: string;
  signInPath: string;
  signOutPath: string;
};

function normalizeOrigin(value: string | undefined): string {
  const candidate = (value ?? DEFAULT_API_ORIGIN).trim().replace(/\/+$/, "");
  const parsed = new URL(candidate);
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("LUMI_API_ORIGIN must use http or https");
  }
  if (parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new Error("LUMI_API_ORIGIN must be an origin without credentials, path, query, or hash");
  }
  return parsed.origin;
}

function normalizeApiPath(value: string | undefined, fallback: string): string {
  const candidate = (value ?? fallback).trim();
  if (!candidate.startsWith("/api/") || candidate.startsWith("//") || candidate.includes("://")) {
    throw new Error("Configured API paths must be same-origin /api/ paths");
  }
  return candidate;
}

export function getWebRuntimeConfig(): WebRuntimeConfig {
  return {
    apiOrigin: normalizeOrigin(process.env.LUMI_API_ORIGIN),
    sessionPath: normalizeApiPath(process.env.LUMI_SESSION_PATH, DEFAULT_SESSION_PATH),
    signInPath: normalizeApiPath(process.env.LUMI_SIGN_IN_PATH, DEFAULT_SIGN_IN_PATH),
    signOutPath: normalizeApiPath(process.env.LUMI_SIGN_OUT_PATH, DEFAULT_SIGN_OUT_PATH),
  };
}

export function requireApiPath(path: string): string {
  if (!path.startsWith("/api/") || path.startsWith("//") || path.includes("://")) {
    throw new Error("API client only accepts same-origin /api/ paths");
  }
  return path;
}
