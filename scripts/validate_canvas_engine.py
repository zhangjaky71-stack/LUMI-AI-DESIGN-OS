from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANVAS = ROOT / "packages/canvas-sdk/src"

REQUIRED_MODULES = {
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
    require("viewportWorldRect" in camera, "Viewport culling camera contract missing")
    require("wheelZoom" in controller and "fitFrame" in controller, "Infinite camera controller missing")
    require("SET_PROPERTY" not in camera, "Camera module must never write Design IR properties")


def validate_render_boundary() -> None:
    renderer = read(CANVAS / "renderer.ts")
    bindings = read(CANVAS / "pixi-v8-bindings.ts")
    require("CanvasRendererAdapter" in renderer, "Renderer adapter contract missing")
    require("PixiV8RendererAdapter" in renderer, "Pixi v8 adapter missing")
    require("createPixiV8Bindings" in bindings, "Concrete Pixi v8 bindings missing")
    require("Object.defineProperty" in bindings, "Pixi handles must use runtime-only identity wrapper")


def validate_interaction_contracts() -> None:
    text = read(CANVAS / "text-edit.ts")
    resources = read(CANVAS / "resource-manager.ts")
    clipboard = read(CANVAS / "clipboard.ts")
    selection = read(CANVAS / "selection.ts")
    require("compositionStart" in text and "compositionEnd" in text, "IME composition boundary missing")
    require("Intl.Segmenter" in text, "Grapheme-aware text handling missing")
    require("CanvasAssetResolver" in resources, "Authorized asset resolver boundary missing")
    require('"runtime:"' in clipboard and '"pixi:"' in clipboard, "Clipboard runtime metadata sanitization missing")
    require("accessibleRows" in selection, "DOM-accessible layers representation missing")


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
    validate_performance_contract()
    print("NODE-40 Canvas Engine architecture contract: OK")


if __name__ == "__main__":
    main()
