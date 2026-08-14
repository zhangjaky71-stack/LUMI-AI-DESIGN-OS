const CONTROL = /[\u0000-\u001f\u007f]/g;
const RESERVED = /[<>:"/\\|?*]/g;
const SENSITIVE_KEY = /(?:^|_)(?:api_?key|secret|authorization|access_?token|refresh_?token|provider_?token|hidden_?prompt|system_?prompt)(?:$|_)/i;

export function sanitizeExportFilename(input: string, fallback = "export"): string {
  const normalized = input.normalize("NFC").replace(CONTROL, "").replace(RESERVED, "_").trim();
  const collapsed = normalized.replace(/\s+/g, " ").replace(/\.{2,}/g, ".");
  const withoutTraversal = collapsed.replace(/^\.+/, "").replace(/\.+$/, "").trim();
  const safe = withoutTraversal || fallback;
  return safe.slice(0, 180);
}

export function safeZipEntryName(input: string): string {
  const normalized = input.normalize("NFC").replace(/\\/g, "/");
  if (normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized)) {
    throw new Error("EXPORT_ZIP_ABSOLUTE_PATH_FORBIDDEN");
  }
  const segments = normalized.split("/").filter(Boolean);
  if (!segments.length) throw new Error("EXPORT_ZIP_ENTRY_EMPTY");
  if (segments.some((segment) => segment === "." || segment === "..")) {
    throw new Error("EXPORT_ZIP_TRAVERSAL_FORBIDDEN");
  }
  return segments.map((segment) => sanitizeExportFilename(segment, "file")).join("/");
}

export function assertExportProfile(profile: string | undefined): void {
  if (profile === "CMYK") throw new Error("EXPORT_CMYK_NOT_SUPPORTED_V1");
  if (profile === "DISPLAY_P3") throw new Error("EXPORT_DISPLAY_P3_NOT_VERIFIED_V1");
  if (profile !== undefined && profile !== "SRGB") throw new Error("EXPORT_COLOR_PROFILE_UNSUPPORTED");
}

export function assertExportFormat(format: string): void {
  const supported = new Set(["PNG", "JPEG", "WEBP", "SVG", "PDF", "LUMI_PACKAGE", "ZIP"]);
  if (format === "PSD") throw new Error("EXPORT_PSD_NOT_SUPPORTED");
  if (!supported.has(format)) throw new Error("EXPORT_FORMAT_UNSUPPORTED");
}

export function assertNoSensitiveExportMetadata(value: unknown, path = "$", depth = 0): void {
  if (depth > 24) throw new Error("EXPORT_METADATA_TOO_DEEP");
  if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") return;
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoSensitiveExportMetadata(item, `${path}[${index}]`, depth + 1));
    return;
  }
  if (typeof value !== "object") throw new Error(`EXPORT_METADATA_VALUE_UNSUPPORTED:${path}`);
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (SENSITIVE_KEY.test(key)) throw new Error(`EXPORT_SENSITIVE_METADATA_FORBIDDEN:${path}.${key}`);
    assertNoSensitiveExportMetadata(child, `${path}.${key}`, depth + 1);
  }
}
