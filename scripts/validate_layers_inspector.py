#!/usr/bin/env python3
"""Static architecture gate for NODE-56 Layers / Inspector UI."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "apps/web/src/components/layers-inspector/layers-inspector.tsx",
    "apps/web/src/components/layers-inspector/layers-inspector.module.css",
    "apps/web/src/lib/layers-inspector/types.ts",
    "apps/web/src/lib/layers-inspector/model.ts",
    "apps/web/src/lib/layers-inspector/operations.ts",
    "apps/web/src/lib/layers-inspector/model.test.ts",
    "apps/web/src/lib/layers-inspector/operations.test.ts",
    "apps/web/e2e/layers-inspector.spec.ts",
    "docs/nodes/NODE-56-LAYERS-INSPECTOR-UI.md",
    "docs/runtime/LAYERS-INSPECTOR-V1.md",
    "reports/nodes/NODE-56/acceptance.md",
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

canvas = read("apps/web/src/components/infinite-canvas/infinite-canvas.tsx")
workspace = read("apps/web/src/components/ai-workspace/ai-workspace.tsx")
inspector = read("apps/web/src/components/layers-inspector/layers-inspector.tsx")
model = read("apps/web/src/lib/layers-inspector/model.ts")
operations = read("apps/web/src/lib/layers-inspector/operations.ts")
e2e = read("apps/web/e2e/layers-inspector.spec.ts")

checks = [
    ("workspace mounts LayersInspector", "<LayersInspector" in workspace),
    ("Canvas publishes editor state", "onEditorStateChange" in canvas and "buildCanvasEditorState" in canvas),
    ("Canvas exposes editor API", "editorRef.current = editorApi" in canvas),
    ("Layers selection drives Canvas", "editorRef.current?.select" in inspector),
    ("visibility uses DesignOperation channel", "setVisibility" in canvas and '"visible"' in canvas),
    ("lock uses DesignOperation channel", "setLocked" in canvas and '"locked"' in canvas),
    ("transform inspector exists", "setTransform" in inspector and "transformOperations" in operations),
    ("typography inspector exists", "Typography" in inspector and "textOperations" in operations),
    ("appearance inspector exists", "Opacity %" in inspector and '"blend_mode"' in canvas),
    ("group uses CREATE + REPARENT", '"CREATE_NODE"' in operations and '"REPARENT_NODE"' in operations),
    ("ungroup removes group", "ungroupOperations" in operations and '"DELETE_NODE"' in operations),
    ("layer ordering uses REORDER_NODE", '"REORDER_NODE"' in operations),
    ("effective visibility/lock projected", "effective_visible" in model and "effective_locked" in model),
    ("AI saved-state gate remains", 'canvasSyncState !== "SAVED"' in workspace),
    ("mobile Inspector regression exists", "mobile Inspector tab" in e2e),
]
for label, passed in checks:
    if not passed:
        errors.append(f"architecture check failed: {label}")

for forbidden in ("localStorage", "sessionStorage", "indexedDB"):
    if forbidden in inspector or forbidden in model or forbidden in operations:
        errors.append(f"Layers/Inspector must not create durable browser truth: {forbidden}")

if "executeOperations" in inspector:
    errors.append("Inspector UI must not execute Design IR directly; commands belong to Canvas runtime")

if errors:
    print("NODE-56 Layers / Inspector validation FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("NODE-56 Layers / Inspector validation PASSED")
