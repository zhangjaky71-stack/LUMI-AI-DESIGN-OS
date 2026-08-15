#!/usr/bin/env python3
"""Static architecture gate for NODE-55 Infinite Canvas UI."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "apps/web/src/components/infinite-canvas/infinite-canvas.tsx",
    "apps/web/src/components/infinite-canvas/infinite-canvas.module.css",
    "apps/web/src/lib/infinite-canvas/types.ts",
    "apps/web/src/lib/infinite-canvas/autosave.ts",
    "apps/web/src/lib/infinite-canvas/viewport.ts",
    "apps/web/src/lib/infinite-canvas/canvas-gateway.ts",
    "apps/web/src/lib/infinite-canvas/canvas-server.ts",
    "apps/web/src/lib/infinite-canvas/autosave.test.ts",
    "apps/web/src/lib/infinite-canvas/canvas-gateway.test.ts",
    "apps/web/src/lib/infinite-canvas/viewport.test.ts",
    "apps/web/e2e/infinite-canvas.spec.ts",
    "docs/runtime/INFINITE-CANVAS-V1.md",
    "reports/nodes/NODE-55/acceptance.md",
]

errors: list[str] = []


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        errors.append(f"missing required file: {path}")
        return ""
    return target.read_text(encoding="utf-8")


for path in REQUIRED:
    read(path)

component = read("apps/web/src/components/infinite-canvas/infinite-canvas.tsx")
autosave = read("apps/web/src/lib/infinite-canvas/autosave.ts")
gateway = read("apps/web/src/lib/infinite-canvas/canvas-gateway.ts")
server = read("apps/web/src/lib/infinite-canvas/canvas-server.ts")
workspace = read("apps/web/src/components/ai-workspace/ai-workspace.tsx")
route = read("apps/web/src/app/app/projects/[projectId]/workspace/page.tsx")
tsconfig = read("apps/web/tsconfig.json")
perf_test = read("apps/web/src/lib/infinite-canvas/viewport.test.ts")
e2e = read("apps/web/e2e/infinite-canvas.spec.ts")

checks = [
    ("web aliases Canvas SDK", '"@lumi/canvas-sdk"' in tsconfig),
    ("web aliases Design IR", '"@lumi/design-ir"' in tsconfig),
    ("route server-selects canvas bootstrap", "getInfiniteCanvasBootstrap" in route),
    ("CanvasController is the product runtime", "new CanvasController" in component),
    ("Canvas transform session is used", "beginTransform" in component and "commitTransform" in component),
    ("multi-frame presets exist", all(token in component for token in ['"1:1"', '"4:5"', '"9:16"', '"16:9"'])),
    ("pan/zoom/fit controls exist", all(token in component for token in ["wheelZoom", "fitAll", "fitSelection", "pan("])),
    ("Asset drag source exists", "application/x-lumi-asset" in component),
    ("Artifact drag source exists", "application/x-lumi-artifact" in component),
    ("DesignOperations are buffered", "CanvasAutosaveBuffer" in component and "DesignOperation" in component),
    ("autosave rebases operation versions", "rebaseOperationsVersion" in autosave),
    ("version conflict is explicit", "DOCUMENT_VERSION_CONFLICT" in gateway and '"CONFLICT"' in component),
    ("explicit Rebase and Reload exist", "Rebase local commands" in component and "Reload canonical" in component),
    ("AI Send waits for saved Canvas", 'canvasSyncState !== "SAVED"' in workspace),
    ("AI receives Canvas selection context", "onContextChange" in component and "selected_node_ids" in workspace),
    ("viewport culling exists", "cullSceneNodes" in component),
    ("2k node performance fixture exists", "2_000" in perf_test),
    ("locked delete is tested", "locked nodes expose safe context actions" in e2e),
    (
        "E2E adapter is production-forbidden",
        'process.env.NODE_ENV !== "production"' in server
        and 'process.env.LUMI_INFINITE_CANVAS_E2E === "1"' in server,
    ),
]
for label, passed in checks:
    if not passed:
        errors.append(f"architecture check failed: {label}")

for forbidden in ("localStorage", "sessionStorage", "indexedDB"):
    if forbidden in component or forbidden in gateway:
        errors.append(f"canonical Canvas state must not use browser durable storage: {forbidden}")

if "artboard" in workspace and "InfiniteCanvasProduct" not in workspace:
    errors.append("NODE-54 static artboard still owns the product Canvas")

if errors:
    print("NODE-55 Infinite Canvas validation FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("NODE-55 Infinite Canvas validation PASSED")
