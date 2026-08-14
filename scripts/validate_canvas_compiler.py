from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANVAS = ROOT / "packages/canvas-sdk/src"

REQUIRED = {
    "compiler-types.ts",
    "compiler-resolvers.ts",
    "compiler-dirty.ts",
    "compiler-cache.ts",
    "compiler.ts",
    "compiler.test.ts",
    "compiler-renderer.test.ts",
    "compiler-benchmark.ts",
    "compiler-benchmark.test.ts",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def validate_modules() -> None:
    missing = sorted(name for name in REQUIRED if not (CANVAS / name).exists())
    require(not missing, f"NODE-41 compiler modules missing: {missing}")


def validate_domain_boundary() -> None:
    compiler = read(CANVAS / "compiler.ts")
    types = read(CANVAS / "compiler-types.ts")
    require("validateDocument" in compiler, "compiler must validate Design IR before projection")
    require("canonicalSha256" in compiler, "compiler must emit deterministic SHA-256 provenance")
    require("CANVAS_COMPILER_VERSION" in types, "compiler version contract missing")
    require("CanvasCompileProvenance" in types, "compiler provenance contract missing")
    require("Pixi" not in compiler, "compiler core must remain renderer-neutral")
    require("pixi" not in types.lower(), "compiler types must not depend on Pixi runtime")


def validate_incremental_boundary() -> None:
    compiler = read(CANVAS / "compiler.ts")
    dirty = read(CANVAS / "compiler-dirty.ts")
    require("incrementalCompile" in compiler, "incremental compiler missing")
    require("fullCompile" in compiler, "full compiler missing")
    require("planCompilerDirtyNodes" in dirty, "dirty planner missing")
    require("descendants" in dirty and "ancestors" in dirty, "dirty dependency expansion missing")
    require("changedResources" in dirty, "resource-dependent invalidation missing")
    require("INCREMENTAL_FALLBACK" in compiler, "safe full-compile fallback missing")


def validate_resource_boundary() -> None:
    resolvers = read(CANVAS / "compiler-resolvers.ts")
    types = read(CANVAS / "compiler-types.ts")
    require("CompilerAssetResolver" in types, "authorized asset resolver contract missing")
    require("CompilerFontResolver" in types, "font resolver contract missing")
    require("CompilerStyleResolver" in types, "style resolver contract missing")
    require("CompilerTextMeasurer" in types, "text measurement contract missing")
    require("DocumentCompilerAssetResolver" in resolvers, "offline asset resolver missing")
    require("DeterministicTextMeasurer" in resolvers, "deterministic text fixture measurer missing")


def validate_canvas_integration() -> None:
    controller = read(CANVAS / "controller.ts")
    renderer = read(CANVAS / "renderer.ts")
    bindings = read(CANVAS / "pixi-v8-bindings.ts")
    require("CanvasSceneCompilerPort" in controller, "CanvasController compiler injection missing")
    require("new CanvasCompiler" in controller, "CanvasController default compiler missing")
    require("compileStructure" in controller, "CanvasController must compile scene before rendering")
    require("resolved_style" in renderer, "renderer compiled style bridge missing")
    require("setMask" in renderer and "setMask" in bindings, "compiled mask materialization missing")
    require("fontFamily" in bindings and "fontSize" in bindings, "compiled text style materialization missing")


def validate_determinism() -> None:
    compiler = read(CANVAS / "compiler.ts")
    test = read(CANVAS / "compiler.test.ts")
    require("hashableResource" in compiler, "resource URI exclusion hash boundary missing")
    require("compile_hash" in compiler, "compile hash provenance missing")
    require("expiring URI" in test, "signed URL determinism regression test missing")
    require("matches a fresh full compile" in test, "incremental/full equivalence test missing")


def validate_benchmark() -> None:
    benchmark = read(CANVAS / "compiler-benchmark.ts")
    test = read(CANVAS / "compiler-benchmark.test.ts")
    require("2_000" in benchmark or "2_000" in test, "2k compiler benchmark missing")
    require("100" in benchmark and "100" in test, "100-operation compiler benchmark missing")
    require("equivalent_compile_hash" in benchmark, "benchmark equivalence signal missing")


def main() -> None:
    validate_modules()
    validate_domain_boundary()
    validate_incremental_boundary()
    validate_resource_boundary()
    validate_canvas_integration()
    validate_determinism()
    validate_benchmark()
    print("NODE-41 Canvas Compiler architecture contract: OK")


if __name__ == "__main__":
    main()
