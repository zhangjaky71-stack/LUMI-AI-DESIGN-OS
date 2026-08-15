#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
required = [
    "apps/web/src/app/app/projects/[projectId]/export/page.tsx",
    "apps/web/src/components/export-ui/export-ui.tsx",
    "apps/web/src/components/export-ui/export-ui.module.css",
    "apps/web/src/lib/export-ui/types.ts",
    "apps/web/src/lib/export-ui/contracts.ts",
    "apps/web/src/lib/export-ui/export-gateway.ts",
    "apps/web/src/lib/export-ui/export-server.ts",
    "apps/web/src/lib/export-ui/contracts.test.ts",
    "apps/web/src/lib/export-ui/export-gateway.test.ts",
    "apps/web/e2e/export-ui.spec.ts",
    "docs/nodes/NODE-60-EXPORT-UI.md",
    "docs/runtime/EXPORT-UI-V1.md",
    "reports/nodes/NODE-60/acceptance.md",
    ".github/workflows/export-ui.yml",
]
errors = []
for rel in required:
    if not (ROOT / rel).exists(): errors.append(f"missing required file: {rel}")

def text(rel): return (ROOT / rel).read_text(encoding="utf-8")

if not errors:
    contracts = text("apps/web/src/lib/export-ui/contracts.ts")
    gateway = text("apps/web/src/lib/export-ui/export-gateway.ts")
    component = text("apps/web/src/components/export-ui/export-ui.tsx")
    server = text("apps/web/src/lib/export-ui/export-server.ts")
    e2e = text("apps/web/e2e/export-ui.spec.ts")
    doc = text("docs/runtime/EXPORT-UI-V1.md")
    combined = "\n".join([contracts, gateway, component, server])

    checks = {
        "canonical artifact-sdk export types": '@lumi/artifact-sdk' in contracts and '@lumi/artifact-sdk' in gateway,
        "exact ArtifactVersion and DesignVersion": "artifact_version_id" in contracts and "design_document_version_id" in contracts and "MUST_BE_EXACT" in contracts,
        "no floating latest resolution": "FLOATING_VERSION" in contracts,
        "dynamic capability filtering": "capabilitiesForSource" in contracts and "supports_vector" in contracts,
        "unsupported print/PSD hidden": "CMYK" in component and "PSD" in component and "crop marks" in component,
        "JPEG alpha fails closed": "EXPORT_JPEG_ALPHA_UNSUPPORTED" in contracts,
        "SCALE/CROP only": 'resize_mode' in contracts and '"SCALE"' in component and '"CROP"' in component,
        "AI Adapt creates version first": "new DesignVersion" in component and "adaptFromDesignVersion" in component,
        "canonical lifecycle labels": all(x in contracts for x in ["PENDING", "RENDERING", "PACKAGING", "VALIDATING", "READY", "FAILED", "EXPIRED"]),
        "READY-only signed download": 'job.status !== "READY"' in gateway and "getDownload" in gateway,
        "signed URL refresh is ephemeral": "ExportDownloadLease" in component and "setLease" in component,
        "history keeps exact source": "artifact_version_id" in component and "design_document_version_id" in component,
        "partial retry not faked": "partial_retry_supported: false" in server and "Per-frame retry is intentionally unavailable" in component,
        "zero AI export cost": "ai_generation_cost: 0" in contracts,
        "deterministic fixture non-production gated": 'process.env.NODE_ENV !== "production"' in server and "LUMI_EXPORT_UI_E2E" in server,
        "browser coverage": all(x in e2e for x in ["exact version", "aspect ratio", "signed link", "batch source", "mobile viewport"]),
        "runtime truth doc": all(x in doc for x in ["ExportRequest", "ExportJob", "ExportResult", "NODE-49", "partial retry"]),
    }
    for name, ok in checks.items():
        if not ok: errors.append(f"contract check failed: {name}")

    for forbidden in ["localStorage", "sessionStorage", "indexedDB", "DESIGN_ADAPTATION"]:
        if forbidden in combined: errors.append(f"forbidden browser/export behavior found: {forbidden}")

if errors:
    print("NODE-60 Export UI validation FAILED")
    for error in errors: print(f" - {error}")
    sys.exit(1)
print("NODE-60 Export UI validation PASS")
