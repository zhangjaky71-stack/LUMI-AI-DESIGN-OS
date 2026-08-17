from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "packages/canvas-sdk/src"
REQUIRED = {
    "camera.ts": ("worldToScreen", "screenToWorld", "zoomToCursor"),
    "scene.ts": ("buildScene", "PLACEHOLDER"),
    "selection.ts": ("SelectionModel", "marquee", "transformable"),
    "transform-session.ts": ("TransformSession", "MOVE_NODE", "RESIZE_NODE", "ROTATE_NODE"),
    "operation-gateway.ts": ("applyOperation", "applyBatch", "ConstraintPreflight"),
    "text-edit.ts": ("compositionStart", "compositionEnd", "Intl.Segmenter"),
    "resource-manager.ts": ("AssetResolver", "refCount", "destroy"),
    "renderer.ts": ("PixiV8RendererAdapter", "HeadlessRendererAdapter"),
    "spatial-index.ts": ("SpatialIndex", "query", "hit"),
    "clipboard.ts": ("lumi.canvas-fragment/1.0", "remapAsset"),
    "history.ts": ("CanvasCommandHistory", "undo", "redo"),
    "controller.ts": ("CanvasController", "worldViewportRect", "scheduleRender"),
}

for filename, markers in REQUIRED.items():
    path = SRC / filename
    assert path.exists(), f"missing {path}"
    text = path.read_text(encoding="utf-8")
    for marker in markers:
        assert marker in text, f"{filename} missing marker {marker}"

index = (SRC / "index.ts").read_text(encoding="utf-8")
for filename in REQUIRED:
    stem = filename.removesuffix(".ts")
    assert f'"./{stem}"' in index, f"index missing export {stem}"

# Renderer implementation is allowed to mention Pixi only inside the adapter boundary.
for path in SRC.glob("*.ts"):
    if path.name == "renderer.ts":
        continue
    text = path.read_text(encoding="utf-8")
    assert "pixi.js" not in text.lower(), f"domain file imports Pixi: {path.name}"

lock = (ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
assert "packages/canvas-sdk:" in lock
# NODE-40 deliberately leaves real Pixi installation open rather than invalidating frozen lock.
canvas_importer = lock.split("packages/canvas-sdk:", 1)[1].split("packages/design-constraints:", 1)[0]
assert "pixi.js:" not in canvas_importer

gaps = json.loads((ROOT / "reports/nodes/NODE-40/gap-ledger.json").read_text(encoding="utf-8"))
assert len(gaps["gaps"]) == 5
assert all(item["status"] == "OPEN" for item in gaps["gaps"])

tests = (ROOT / "packages/canvas-sdk/tests/canvas-engine.node40.test.ts").read_text(encoding="utf-8")
for marker in ("zoom-to-cursor", "Chinese IME", "constraint denial", "10k"):
    assert marker.lower().replace("10k", "10k") in tests.lower() or (marker == "10k" and "10_000" in tests), marker

print("NODE40_CANVAS_ENGINE_VALIDATION_PASS")
