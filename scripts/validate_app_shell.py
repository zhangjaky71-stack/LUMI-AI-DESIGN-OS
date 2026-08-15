#!/usr/bin/env python3
"""Static architecture/security gate for NODE-52 App Shell."""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"

REQUIRED = [
    "apps/web/src/app/layout.tsx",
    "apps/web/src/app/login/page.tsx",
    "apps/web/src/app/signup/page.tsx",
    "apps/web/src/app/app/layout.tsx",
    "apps/web/src/app/app/projects/page.tsx",
    "apps/web/src/app/app/projects/[projectId]/page.tsx",
    "apps/web/src/app/app/brands/page.tsx",
    "apps/web/src/app/app/assets/page.tsx",
    "apps/web/src/app/app/team/page.tsx",
    "apps/web/src/app/app/billing/page.tsx",
    "apps/web/src/app/app/settings/page.tsx",
    "apps/web/src/app/admin/page.tsx",
    "apps/web/src/app/app/loading.tsx",
    "apps/web/src/app/app/error.tsx",
    "apps/web/src/app/global-error.tsx",
    "apps/web/src/components/app-shell/app-shell-frame.tsx",
    "apps/web/src/components/app-shell/shell-context.tsx",
    "apps/web/src/lib/app-shell/auth-server.ts",
    "apps/web/src/lib/app-shell/api-client.ts",
    "apps/web/src/lib/app-shell/query-cache.ts",
    "apps/web/src/lib/app-shell/telemetry.ts",
    "apps/web/src/lib/app-shell/feature-flags.server.ts",
    "apps/web/e2e/app-shell.spec.ts",
]

errors: list[str] = []

for rel in REQUIRED:
    if not (ROOT / rel).exists():
        errors.append(f"missing required file: {rel}")


def read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""

root_layout = read("apps/web/src/app/layout.tsx")
app_layout = read("apps/web/src/app/app/layout.tsx")
auth_server = read("apps/web/src/lib/app-shell/auth-server.ts")
api_client = read("apps/web/src/lib/app-shell/api-client.ts")
query_cache = read("apps/web/src/lib/app-shell/query-cache.ts")
telemetry = read("apps/web/src/lib/app-shell/telemetry.ts")
globals_css = read("apps/web/src/app/globals.css")

if '"use client"' in root_layout or "'use client'" in root_layout:
    errors.append("root layout must remain a Server Component")
if "requireShellSession" not in app_layout or 'dynamic = "force-dynamic"' not in app_layout:
    errors.append("/app layout must use server-side session boundary and dynamic rendering")
if "LUMI_SHELL_E2E_AUTH" not in auth_server or "return null" not in auth_server:
    errors.append("auth adapter must be explicit E2E-only and fail closed when NODE-16 is unavailable")

for marker in ["/api/v1", "x-request-id", "x-lumi-organization-id", "x-csrf-token", "idempotency-key", "if-match"]:
    if marker not in api_client:
        errors.append(f"API client missing contract marker: {marker}")
if 'method === "GET" ? 3 : 1' not in api_client:
    errors.append("API retry policy must be GET-only")
if "[this.#organizationId, ...parts]" not in query_cache or "abortInFlight" not in query_cache:
    errors.append("query cache must key by organization and abort old in-flight work")
if "TELEMETRY_SENSITIVE_PROPERTY_FORBIDDEN" not in telemetry:
    errors.append("telemetry adapter must reject sensitive fields")
for marker in ["--ui-bg", "--space-4", "--radius-md", "--shadow-float", "--z-dialog", "--motion-base", "prefers-reduced-motion"]:
    if marker not in globals_css:
        errors.append(f"UI token/accessibility marker missing: {marker}")

raw_fetch_allowed = (WEB / "lib" / "app-shell" / "api-client.ts").resolve()
for path in WEB.rglob("*"):
    if path.suffix not in {".ts", ".tsx"} or path.name.endswith(".test.ts"):
        continue
    resolved = path.resolve()
    if "canvas-engine" in path.parts or "canvas-spike" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    if resolved != raw_fetch_allowed and re.search(r"\bfetch\s*\(", text):
        errors.append(f"raw fetch outside API client: {path.relative_to(ROOT)}")
    if (text.startswith('"use client"') or text.startswith("'use client'")) and "process.env" in text:
        errors.append(f"client component reads process.env: {path.relative_to(ROOT)}")
    if (text.startswith('"use client"') or text.startswith("'use client'")) and (
        "auth-server" in text or "feature-flags.server" in text
    ):
        errors.append(f"client imports server-only shell module: {path.relative_to(ROOT)}")
    if "localStorage" in text or "sessionStorage" in text:
        errors.append(f"business/session truth must not live in browser storage: {path.relative_to(ROOT)}")

secret_pattern = re.compile(r"NEXT_PUBLIC_[A-Z0-9_]*(SECRET|PASSWORD|PRIVATE|TOKEN|API_KEY|SERVICE_KEY)")
for path in (ROOT / "apps" / "web").rglob("*"):
    if path.is_file() and path.suffix in {".ts", ".tsx", ".js", ".mjs", ".json"}:
        text = path.read_text(encoding="utf-8")
        if secret_pattern.search(text):
            errors.append(f"client-visible secret-like environment variable: {path.relative_to(ROOT)}")

for rel in ["apps/web/src/app/app/error.tsx", "apps/web/src/app/app/projects/[projectId]/error.tsx"]:
    text = read(rel)
    if "error.stack" in text or "error.message" in text:
        errors.append(f"error boundary leaks internal exception text: {rel}")

if errors:
    print("NODE-52 APP SHELL VALIDATION FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("NODE-52 APP SHELL VALIDATION PASSED")
