from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = [
    "packages/canvas-sdk/src/compiler-types.ts",
    "packages/canvas-sdk/src/compiler-math.ts",
    "packages/canvas-sdk/src/compiler-resolvers.ts",
    "packages/canvas-sdk/src/compiler-dirty.ts",
    "packages/canvas-sdk/src/compiler-hash.ts",
    "packages/canvas-sdk/src/compiler.ts",
    "packages/canvas-sdk/src/compiler-renderer.ts",
    "packages/canvas-sdk/src/compiler-runtime.ts",
    "packages/canvas-sdk/src/compiler-benchmark.ts",
    "packages/canvas-sdk/tests/canvas-compiler.node41.test.ts",
    "packages/canvas-sdk/fixtures/compiler-snapshot-v1.json",
    "docs/runtime/CANVAS-COMPILER-V1.md",
    "reports/nodes/NODE-41/gap-ledger.json",
    "reports/nodes/NODE-41/acceptance.md",
    ".github/workflows/node-41-canvas-compiler.yml",
]

missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
if missing:
    raise SystemExit(f"NODE41_MISSING_FILES: {missing}")

compiler_files = list((ROOT / "packages/canvas-sdk/src").glob("compiler*.ts"))
source = "\n".join(path.read_text(encoding="utf-8") for path in compiler_files)
for forbidden in ('from "pixi.js"', "from 'pixi.js'", "@pixi/"):
    if forbidden in source:
        raise SystemExit(f"NODE41_RENDERER_COUPLING_FORBIDDEN: {forbidden}")

required_tokens = [
    "CANVAS_COMPILER_VERSION",
    "compileFull",
    "compileIncremental",
    "compileResourceInvalidation",
    "recordProvenance",
    "validateDocument",
    "computeSemanticDiff",
    "CompiledSceneNode",
    "CompiledScenePatch",
    "CanvasCompilerRendererRuntime",
    "authorizedUrl",
    "resourceVersion",
    "renderFingerprint",
]
for token in required_tokens:
    if token not in source:
        raise SystemExit(f"NODE41_REQUIRED_TOKEN_MISSING: {token}")

fixture = json.loads((ROOT / "packages/canvas-sdk/fixtures/compiler-snapshot-v1.json").read_text())
if fixture.get("schema") != "lumi.canvas-compiler.fixture.v1":
    raise SystemExit("NODE41_FIXTURE_SCHEMA_INVALID")
if fixture.get("compilerVersion") != "1.0.0":
    raise SystemExit("NODE41_FIXTURE_COMPILER_VERSION_INVALID")
if len(fixture.get("orderedIds", [])) != 5:
    raise SystemExit("NODE41_FIXTURE_NODE_COUNT_INVALID")

gaps = json.loads((ROOT / "reports/nodes/NODE-41/gap-ledger.json").read_text())
if gaps.get("node") != "NODE-41" or len(gaps.get("gaps", [])) != 5:
    raise SystemExit("NODE41_GAP_LEDGER_INVALID")
if any(item.get("status") != "OPEN" for item in gaps["gaps"]):
    raise SystemExit("NODE41_GAP_STATUS_INVALID")

index = (ROOT / "packages/canvas-sdk/src/index.ts").read_text()
for export in ("./compiler", "./compiler-renderer", "./compiler-runtime", "./compiler-types"):
    if export not in index:
        raise SystemExit(f"NODE41_PUBLIC_EXPORT_MISSING: {export}")

print("NODE41_CANVAS_COMPILER_VALIDATION_PASS")
