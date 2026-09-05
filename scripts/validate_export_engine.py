from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "packages/artifact-sdk/src"
ENGINE = SDK / "export-engine.ts"
TYPES = SDK / "export-engine-types.ts"
SECURITY = SDK / "export-security.ts"
SOURCE = SDK / "export-source-adapter.ts"
SVG = SDK / "export-svg.ts"
PDF = SDK / "export-pdf.ts"
ZIP = SDK / "export-zip.ts"
ARTIFACT = SDK / "export-artifact-adapter.ts"
WORKER_PROTOCOL = SDK / "export-worker-protocol.ts"
WORKER = ROOT / "scripts/export-raster-worker.mjs"
WORKER_TEST = ROOT / "scripts/export-raster-worker.test.mjs"
MIGRATION = ROOT / "db/migrations/0008_export_engine.sql"
FIXTURE = ROOT / "fixtures/export-engine/node-49-conformance.json"
TESTS = SDK / "export-engine-v1.test.ts"
SOURCE_TEST = SDK / "export-source-adapter.test.ts"
ARTIFACT_TEST = SDK / "export-artifact-adapter.test.ts"
PACKAGE_TEST = SDK / "export-package.test.ts"
ROOT_PACKAGE = ROOT / "package.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: Path) -> str:
    require(path.exists(), f"missing required file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def main() -> None:
    fixture = json.loads(read(FIXTURE))
    require(int(fixture["synthetic_case_count"]) >= 60, "conformance matrix too small")
    require(set(fixture["formats"]) == {"PNG", "JPEG", "WEBP", "SVG", "PDF", "ZIP", "LUMI_PACKAGE"}, "format fixture drift")

    engine = read(ENGINE)
    types = read(TYPES)
    security = read(SECURITY)
    source = read(SOURCE)
    svg = read(SVG)
    pdf = read(PDF)
    zip_code = read(ZIP)
    artifact = read(ARTIFACT)
    worker_protocol = read(WORKER_PROTOCOL)
    worker = read(WORKER)
    worker_test = read(WORKER_TEST)
    migration = read(MIGRATION)
    tests = read(TESTS)
    source_test = read(SOURCE_TEST)
    artifact_test = read(ARTIFACT_TEST)
    package_test = read(PACKAGE_TEST)
    root_package = json.loads(read(ROOT_PACKAGE))

    require("artifact_version_id" in types and "design_document_version_id" in types, "exact source IDs missing")
    require("design_document: unknown" in types and "render_plan: unknown" in types, "exact Design IR/render snapshot missing")
    require("EXPORT_FLOATING_VERSION_FORBIDDEN" in engine, "floating latest rejection missing")
    require("findReadyByFingerprint" in engine and "EXPORT_OPERATION_SEMANTIC_CONFLICT" in engine, "idempotency/reuse contract missing")
    require("DESIGN_ADAPTATION" not in engine, "Export Engine must not perform hidden design adaptation")
    require("EXPORT_PRINT_MARKS_NOT_IMPLEMENTED_V1" in engine, "print marks must fail closed until implemented")
    require("EXPORT_CMYK_NOT_SUPPORTED_V1" in security, "CMYK false-claim guard missing")
    require("EXPORT_DISPLAY_P3_NOT_VERIFIED_V1" in security, "Display P3 false-claim guard missing")
    require("EXPORT_PSD_NOT_SUPPORTED" in security, "PSD false-claim guard missing")
    require("EXPORT_EPHEMERAL_RUNTIME_REF_FORBIDDEN" in security, "runtime URL persistence guard missing")
    require("hidden_?prompt" in security and "system_?prompt" in security, "hidden prompt metadata guard missing")

    require("CompileResult" in source and "if (!compiled.ok)" in source, "NODE-41 compile fail-closed path missing")
    require("durableDesignDocument" in source and "EPHEMERAL_KEY" in source, "Design IR URL stripping missing")
    require("resolved_resource" in source and "uri:" not in source.split("resolved_resource:", 1)[1].split("interaction_flags", 1)[0], "compiler URI leaked into durable render snapshot")
    require("tx:" in svg and "ty:" in svg and "matrix.tx" in svg, "Canvas Matrix2D tx/ty integration missing")
    require("xMidYMid slice" in svg and "xMidYMid meet" in svg, "SCALE/CROP semantics missing")
    require("unit === \"MM\"" in svg and "unit === \"IN\"" in svg, "mm/in conversion missing")
    require("data:image\\/(?:png|jpeg|webp)" in svg, "safe inline raster image policy missing")
    require("EXPORT_VECTOR_PATH_GEOMETRY_REQUIRED" in svg, "vector path fail-closed contract missing")

    require("%PDF-1.7" in pdf and "xref" in pdf and "%%EOF" in pdf, "real PDF writer structure missing")
    require("inspectRasterPdf" in pdf and "MediaBox" in pdf, "independent PDF validation missing")
    require("crc32" in zip_code and "validateCentralDirectory" in zip_code and "findEocd" in zip_code, "ZIP structural validation incomplete")
    require("EXPORT_ZIP_TRAVERSAL_FORBIDDEN" in security, "zip-slip defense missing")
    require('type: "EXPORTED_FROM"' in artifact, "NODE-42 EXPORTED_FROM lineage missing")
    require("attachVerifiedFile" in artifact and "addProvenance" in artifact, "Artifact verified file/provenance missing")

    require("WorkerBackedRasterCodec" in worker_protocol and "EXPORT_RASTER_WORKER_DIMENSIONS_MISMATCH" in worker_protocol, "typed worker protocol missing")
    require('from "@playwright/test"' in worker, "Chromium renderer must use root locked Playwright")
    require("canvas.toBlob" in worker and "verificationImage.decode" in worker, "real raster encode/decode verification missing")
    require("context.route" in worker and "blockedbyclient" in worker, "worker network block missing")
    require("PNG/JPEG/WebP OK" in worker_test, "real raster smoke test missing")
    require(root_package["devDependencies"].get("@playwright/test") == "1.61.1", "Playwright version drift")

    required_sql = (
        "export_jobs",
        "export_files",
        "export_format_validations",
        "export_download_audit",
        "artifact_version_id uuid NOT NULL",
        "compiler_compile_hash char(64)",
        "storage_key text NOT NULL",
        "WHERE status = 'READY'",
    )
    for token in required_sql:
        require(token in migration, f"missing export SQL contract: {token}")
    schema_lines = [line for line in migration.splitlines() if not line.lstrip().startswith("--")]
    schema_text = "\n".join(schema_lines).lower()
    require("signed_url" not in schema_text and "presigned_url" not in schema_text, "signed URL must not be persisted")

    for token in (
        "pins the exact ArtifactVersion and DesignVersion",
        "reuses a READY semantic fingerprint",
        "authorizes each re-download",
        "converts mm/in at DPI",
        "font fallback",
    ):
        require(token in tests, f"missing executable export evidence: {token}")
    require("CanvasCompiler" in source_test and "signed.example" in source_test, "real compiler URL-strip regression missing")
    require("EXPORTED_FROM" in artifact_test, "Artifact lineage regression missing")
    require("LUMI package" in package_test and "CRC" in package_test, "package content/tamper regression missing")

    print("NODE-49 Export Engine architecture contract: OK")


if __name__ == "__main__":
    main()
