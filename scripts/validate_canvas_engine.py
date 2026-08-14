from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANVAS = ROOT / "packages/canvas-sdk/src"
WEB_CANVAS = ROOT / "apps/web/src/app/canvas-engine"
WEB_E2E = ROOT / "apps/web/e2e/canvas-engine.spec.ts"

REQUIRED_MODULES = {
    "asset-residency.ts",
    "matrix.ts",
    "ir-scene.ts",
    "spatial-index.ts",
    "selection.ts",
    "snapping.ts",
    "transform-session.ts",
    "renderer.ts",
    "pixi-v8-bindings.ts",
    "resource-manager.ts",
    "text-edit.ts",
    "clipboard.ts",
    "keyboard.ts",
    "command-bus.ts",
    "controller.ts",
    "runtime-benchmark.ts",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def validate_modules() -> None:
    missing = sorted(name for name in REQUIRED_MODULES if not (CANVAS / name).exists())
    require(not missing, f"NODE-40 canvas modules missing: {missing}")
    require((WEB_CANVAS / "CanvasEngineClient.tsx").exists(), "real browser Canvas Engine harness missing")
    require(WEB_E2E.exists(), "Canvas Engine Playwright E2E missing")


def validate_ir_boundary() -> None:
    ir_root = ROOT / "packages/design-ir/src"
    constraints_root = ROOT / "packages/design-constraints/src"
    for root in (ir_root, constraints_root):
        for path in root.glob("*.ts"):
            content = read(path).lower()
            require("pixi.js" not in content, f"Pixi dependency leaked into domain contract: {path}")
            require("pixidisplay" not in content, f"Pixi runtime object leaked into domain contract: {path}")

    scene = read(CANVAS / "ir-scene.ts")
    require("DesignDocument" in scene, "Canvas scene must project from Design IR")
    require("canonicalStringify" in scene, "Canvas dirty keys must be deterministic")
    require("effectiveVisible" in scene, "ancestor visibility inheritance missing")
    require("effectiveLocked" in scene, "ancestor lock inheritance missing")
    require("pixi.js" not in scene.lower(), "Derived scene must stay renderer-neutral")


def validate_constraint_boundary() -> None:
    transform = read(CANVAS / "transform-session.ts")
    commands = read(CANVAS / "command-bus.ts")
    require("guardedExecute" in transform, "Transform commit must pass NODE-39 guardedExecute")
    require("guardedExecute" in commands, "Undo/redo command bus must pass NODE-39 guardedExecute")
    require("executeOperations" in transform, "Local preview must use NODE-38 operation semantics")


def validate_camera_boundary() -> None:
    camera = read(CANVAS / "camera.ts")
    controller = read(CANVAS / "controller.ts")
    renderer = read(CANVAS / "renderer.ts")
    require("viewportWorldRect" in camera, "Viewport culling camera contract missing")
    require("wheelZoom" in controller and "fitFrame" in controller, "Infinite camera controller missing")
    require("setCamera(this.#camera)" in controller, "Camera must drive actual renderer stage")
    require("setCamera(camera: CameraState)" in renderer, "Renderer camera contract missing")
    require("SET_PROPERTY" not in camera, "Camera module must never write Design IR properties")


def validate_render_boundary() -> None:
    renderer = read(CANVAS / "renderer.ts")
    bindings = read(CANVAS / "pixi-v8-bindings.ts")
    require("CanvasRendererAdapter" in renderer, "Renderer adapter contract missing")
    require("PixiV8RendererAdapter" in renderer, "Pixi v8 adapter missing")
    require("redrawShape" in renderer, "resized vector/frame redraw contract missing")
    require("setDisplaySize" in renderer, "image/video display sizing contract missing")
    require("createPixiV8Bindings" in bindings, "Concrete Pixi v8 bindings missing")
    require("Object.defineProperty" in bindings, "Pixi handles must use runtime-only identity wrapper")
    require("children: false" in bindings, "renderer-owned objects must avoid recursive double-disposal")


def validate_interaction_contracts() -> None:
    text = read(CANVAS / "text-edit.ts")
    resources = read(CANVAS / "resource-manager.ts")
    residency = read(CANVAS / "asset-residency.ts")
    clipboard = read(CANVAS / "clipboard.ts")
    selection = read(CANVAS / "selection.ts")
    controller = read(CANVAS / "controller.ts")
    require("compositionStart" in text and "compositionEnd" in text, "IME composition boundary missing")
    require("Intl.Segmenter" in text, "Grapheme-aware text handling missing")
    require("CanvasAssetResolver" in resources, "Authorized asset resolver boundary missing")
    require("#inflight" in resources and "references += 1" in resources, "shared texture concurrency accounting missing")
    require("CanvasAssetResidency" in residency and ".peek(" in residency, "viewport asset residency/live texture lookup missing")
    require("#assetResidency?.update" in controller, "viewport culling must drive asset residency")
    require('"runtime:"' in clipboard and '"pixi:"' in clipboard, "Clipboard runtime metadata sanitization missing")
    require("accessibleRows" in selection, "DOM-accessible layers representation missing")


def validate_browser_contract() -> None:
    client = read(WEB_CANVAS / "CanvasEngineClient.tsx")
    e2e = read(WEB_E2E)
    require("PixiV8RendererAdapter" in client and "CanvasController" in client, "browser harness must use production Canvas runtime")
    require("lockAndMove" in client and "LOCK_POSITION" in client, "browser hard-constraint path missing")
    require("data-canvas-engine" in client, "real Pixi browser canvas marker missing")
    require("document_version" in e2e and "DENY" in e2e, "browser E2E must verify version-preserving hard rollback")


def validate_performance_contract() -> None:
    benchmark = read(CANVAS / "runtime-benchmark.ts")
    require("CANVAS_SYNC_FRAME_BUDGET_MS = 16.7" in benchmark, "NODE-08 synchronous frame budget drifted")
    require("2_000" in read(CANVAS / "runtime-performance.test.ts"), "2k performance gate missing")
    require("10_000" in read(CANVAS / "runtime-performance.test.ts"), "10k stress gate missing")


def main() -> None:
    validate_modules()
    validate_ir_boundary()
    validate_constraint_boundary()
    validate_camera_boundary()
    validate_render_boundary()
    validate_interaction_contracts()
    validate_browser_contract()
    validate_performance_contract()
    print("NODE-40 Canvas Engine architecture contract: OK")


if __name__ == "__main__":
    main()
