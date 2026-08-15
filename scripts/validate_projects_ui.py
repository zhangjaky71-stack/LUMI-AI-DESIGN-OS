#!/usr/bin/env python3
"""Static architecture/security gate for NODE-53 Projects UI."""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

REQUIRED = [
    "apps/web/src/app/app/projects/page.tsx",
    "apps/web/src/app/app/projects/[projectId]/page.tsx",
    "apps/web/src/components/projects/projects-dashboard.tsx",
    "apps/web/src/components/projects/new-project-dialog.tsx",
    "apps/web/src/components/projects/project-detail.tsx",
    "apps/web/src/components/projects/projects.module.css",
    "apps/web/src/lib/projects/types.ts",
    "apps/web/src/lib/projects/contracts.ts",
    "apps/web/src/lib/projects/client-utils.ts",
    "apps/web/src/lib/projects/projects-gateway.ts",
    "apps/web/src/lib/projects/projects-server.ts",
    "apps/web/src/lib/projects/projects-gateway.test.ts",
    "apps/web/src/lib/projects/presigned-upload.test.ts",
    "apps/web/e2e/projects.spec.ts",
]

errors: list[str] = []

for rel in REQUIRED:
    if not (ROOT / rel).exists():
        errors.append(f"missing required file: {rel}")


def read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


page = read("apps/web/src/app/app/projects/page.tsx")
detail_page = read("apps/web/src/app/app/projects/[projectId]/page.tsx")
dashboard = read("apps/web/src/components/projects/projects-dashboard.tsx")
new_project = read("apps/web/src/components/projects/new-project-dialog.tsx")
detail = read("apps/web/src/components/projects/project-detail.tsx")
gateway = read("apps/web/src/lib/projects/projects-gateway.ts")
server = read("apps/web/src/lib/projects/projects-server.ts")
api_client = read("apps/web/src/lib/app-shell/api-client.ts")
types = read("apps/web/src/lib/projects/types.ts")
e2e = read("apps/web/e2e/projects.spec.ts")
css = read("apps/web/src/components/projects/projects.module.css")

if '"use client"' in page or "'use client'" in page:
    errors.append("Projects route must remain a Server Component boundary")
if '"use client"' in detail_page or "'use client'" in detail_page:
    errors.append("Project detail route must remain a Server Component boundary")
if "getProjectsBootstrap" not in page or "getProjectsBootstrap" not in detail_page:
    errors.append("Project routes must receive server-controlled bootstrap state")

for marker in [
    "LUMI_PROJECTS_E2E",
    'process.env.NODE_ENV !== "production"',
    'mode: "http"',
    'mode: "e2e"',
]:
    if marker not in server:
        errors.append(f"Projects server bootstrap missing safety marker: {marker}")

if "new HttpProjectsGateway(api)" not in gateway:
    errors.append("production/default Projects mode must use HTTP gateway")
if "PROJECTS_E2E_SEED_REQUIRED" not in gateway:
    errors.append("deterministic Projects gateway must require explicit E2E seed")
for marker in [
    "/projects?",
    "/assets/uploads",
    "/archive",
    "/restore",
    "expected_brief_version",
    "VERSION_CONFLICT",
    "scan_status",
    "REJECTED",
]:
    if marker not in gateway:
        errors.append(f"Projects gateway missing contract marker: {marker}")

if "putPresignedObject" not in gateway:
    errors.append("reference upload must use the isolated presigned upload transport")
if "credentials: \"omit\"" not in api_client:
    errors.append("presigned object PUT must omit session credentials")
if "UPLOAD_PRESIGNED_URL_PROTOCOL_FORBIDDEN" not in api_client:
    errors.append("presigned object PUT must reject non-http protocols")

for marker in [
    "source_intent",
    "brand_id",
    "deliverables",
    "budget_microusd",
]:
    if marker not in gateway:
        errors.append(f"minimal project create adapter missing field: {marker}")

for marker in [
    "一句话描述",
    "直接开始",
    "参考文件",
    "高级设置",
    "Brand Kit",
    "创建项目",
]:
    if marker not in new_project:
        errors.append(f"New Project UX missing marker: {marker}")

if "BriefVersion" not in detail or "brief_version" not in detail:
    errors.append("Project detail must expose BriefVersion semantics")
if "archiveProject" not in dashboard or "restoreProject" not in dashboard:
    errors.append("Project dashboard must expose safe archive/restore lifecycle")
if "confirm" in dashboard.lower() and "确认归档" not in dashboard:
    errors.append("archive confirmation must be explicit product UI")
if "永久删除" in dashboard or "永久删除" in new_project:
    errors.append("NODE-53 must not surface destructive permanent-delete UX")

for marker in [
    "ProjectStatus",
    "StructuredBrief",
    "BriefVersion",
    "ReferenceRole",
    "AssetScanStatus",
    "CursorPage",
]:
    if marker not in types:
        errors.append(f"Projects domain type missing: {marker}")

source_paths = [
    ROOT / "apps/web/src/components/projects",
    ROOT / "apps/web/src/lib/projects",
]
for base in source_paths:
    if not base.exists():
        continue
    for path in base.rglob("*"):
        if path.suffix not in {".ts", ".tsx"} or path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        if "localStorage" in text or "sessionStorage" in text:
            errors.append(
                f"Project business truth must not live in browser storage: {path.relative_to(ROOT)}"
            )
        if re.search(r"\bfetch\s*\(", text):
            errors.append(
                f"Projects components/gateway must not bypass LumiApiClient: {path.relative_to(ROOT)}"
            )
        if text.startswith('"use client"') and "process.env" in text:
            errors.append(
                f"Projects client component must not read server environment: {path.relative_to(ROOT)}"
            )

for marker in [
    "search, cursor pagination",
    "natural-language sentence",
    "scanner rejection",
    "Brand and deliverable",
    "rename conflict",
    "archive is confirmed",
    "BriefVersion",
]:
    if marker not in e2e:
        errors.append(f"Projects E2E matrix missing scenario marker: {marker}")

if "@media (max-width: 560px)" not in css or "prefers-reduced-motion" not in css:
    errors.append("Projects UI must retain responsive and reduced-motion behavior")

if errors:
    print("NODE-53 PROJECTS UI VALIDATION FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("NODE-53 PROJECTS UI VALIDATION PASSED")
