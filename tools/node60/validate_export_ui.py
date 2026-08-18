from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(path: str, *markers: str) -> None:
    text = read(path)
    missing = [marker for marker in markers if marker not in text]
    assert not missing, f"{path}: missing {missing}"


def forbid(path: str, *markers: str) -> None:
    text = read(path)
    found = [marker for marker in markers if marker in text]
    assert not found, f"{path}: forbidden {found}"


def main() -> None:
    require(
        "apps/api/src/lumi_api/api/v1/app.py",
        "export_product_router",
        "app.include_router(export_product_router",
    )
    require(
        "apps/api/src/lumi_api/api/v1/export_product_dependencies.py",
        "export_engine_factory",
        "with factory() as engine",
        "export_engine_not_composed",
    )
    require(
        "apps/api/src/lumi_api/api/v1/export_product_routes.py",
        "snapshot_exact",
        "authorize_snapshot",
        "task.project_id != project_id",
        "IdempotencyKey",
        "_operation_id(idempotency_key)",
        "item.target_format not in allowed",
        "engine.issue_download",
        "_scoped_job",
    )
    require(
        "apps/api/src/lumi_api/api/v1/export_product_schemas.py",
        "supports_resize: bool = False",
        "supports_quality: bool = False",
        "supports_alpha: bool = False",
        "supports_print_options: bool = False",
        "supports_ai_adapt: bool = False",
        "class ExportManifestResponse",
        "class ExportDownloadGrantResponse",
    )
    safe_schema = read("apps/api/src/lumi_api/api/v1/export_product_schemas.py")
    assert "storage_key" not in safe_schema
    assert "bucket:" not in safe_schema

    require(
        "apps/web/src/lib/exports/types.ts",
        '"ORIGINAL" | "PNG" | "JPEG" | "MP4" | "PDF" | "PPTX"',
        '"PLANNED" | "QUEUED" | "RENDERING" | "PACKAGING" | "READY" | "FAILED" | "CANCELLED" | "EXPIRED"',
        "parseExportCapabilities",
        "parseExportJob",
        "parseExportDownloadGrant",
    )
    forbid(
        "apps/web/src/lib/exports/types.ts",
        '"WEBP"',
        '"SVG"',
        '"VALIDATING"',
        '"PENDING"',
    )
    require(
        "apps/web/src/components/exports/export-panel.tsx",
        "verified copy-through only",
        "No AI generation fee",
        "Export never resolves “latest”",
        "issueExportDownload",
        "Request Download again after expiry; the READY package is reused",
        "Partial per-item retry is not exposed",
        "PLANNED",
        "QUEUED",
        "RENDERING",
        "PACKAGING",
        "READY",
    )
    forbid(
        "apps/web/src/components/exports/export-panel.tsx",
        "storage_key",
        "window.open(",
        "VALIDATING",
        "PENDING",
    )
    require(
        "apps/web/src/components/workspace/ai-workspace.tsx",
        "ExportPanel",
        "currentArtifact={selectedArtifact}",
        "availableArtifacts={runtime.artifacts}",
    )
    require(
        "apps/web/src/lib/exports/api.ts",
        'task_type: "export"',
        '"Idempotency-Key": crypto.randomUUID()',
        "force_zip: items.length > 1",
        "issueExportDownload",
    )
    for path in (
        "apps/api/tests/test_node60_export_product_contracts.py",
        "apps/web/src/lib/exports/types.test.ts",
        "docs/runtime/EXPORT-PRODUCT-UI-V1.md",
        "reports/nodes/NODE-60/acceptance.md",
        "reports/nodes/NODE-60/gap-ledger.json",
    ):
        assert (ROOT / path).is_file(), f"missing NODE-60 evidence: {path}"

    ledger = json.loads(read("reports/nodes/NODE-60/gap-ledger.json"))
    assert ledger["node"] == "NODE-60"
    assert ledger["status"] == "CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE"
    assert any(item["severity"] == "P0" and item["status"] == "open" for item in ledger["gaps"])
    spec = read("docs/nodes/NODE-60-EXPORT-UI.md")
    assert "CORE IMPLEMENTED / VALIDATING / NOT COMPLETE" in spec
    print("NODE60_EXPORT_UI_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
