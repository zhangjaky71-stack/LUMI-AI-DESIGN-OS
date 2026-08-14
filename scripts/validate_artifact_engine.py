from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    "packages/artifact-sdk/src/types.ts",
    "packages/artifact-sdk/src/engine.ts",
    "packages/artifact-sdk/src/hashing.ts",
    "packages/artifact-sdk/src/compiler-bridge.ts",
    "packages/artifact-sdk/src/export.ts",
    "packages/artifact-sdk/src/gc.ts",
    "services/artifact-history/src/lumi_artifacts/storage.py",
    "services/artifact-history/src/lumi_artifacts/runtime.py",
    "db/migrations/0001_artifact_engine.sql",
]
for path in required:
    if not (ROOT / path).exists():
        raise SystemExit(f"missing NODE-42 contract file: {path}")

engine = (ROOT / "packages/artifact-sdk/src/engine.ts").read_text()
for token in ["expectedBranchHead", "attachVerifiedFile", "restore(", "lineage cycle", "APPROVED"]:
    if token not in engine:
        raise SystemExit(f"artifact engine invariant missing: {token}")

migration = (ROOT / "db/migrations/0001_artifact_engine.sql").read_text()
for table in ["artifacts", "artifact_versions", "artifact_branches", "artifact_edges", "artifact_files", "artifact_provenance"]:
    if f"{table} (" not in migration:
        raise SystemExit(f"artifact migration table missing: {table}")
if "IS NOT DISTINCT FROM :expected" not in migration:
    raise SystemExit("branch CAS SQL contract missing")

bridge = (ROOT / "packages/artifact-sdk/src/compiler-bridge.ts").read_text()
if "CompiledSceneSnapshot" not in bridge or "compile_hash" not in bridge:
    raise SystemExit("NODE-41 compiler provenance bridge missing")

print("NODE-42 artifact engine architecture contract: OK")
