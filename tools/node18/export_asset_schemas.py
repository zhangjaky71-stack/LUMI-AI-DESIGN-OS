from __future__ import annotations

import json
from pathlib import Path

from lumi_api.assets.api import (
    AssetDownloadResponse,
    AssetPreviewListResponse,
    AssetResponse,
    CompleteAssetUploadRequest,
    CreateAssetUploadRequest,
    CreateAssetUploadResponse,
)
from lumi_api.assets.models import UploadSession, ValidationReport

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "nodes" / "NODE-18" / "generated-schemas"

SCHEMAS = {
    "create-asset-upload-request-v1.schema.json": CreateAssetUploadRequest,
    "create-asset-upload-response-v1.schema.json": CreateAssetUploadResponse,
    "complete-asset-upload-request-v1.schema.json": CompleteAssetUploadRequest,
    "asset-response-v1.schema.json": AssetResponse,
    "asset-download-response-v1.schema.json": AssetDownloadResponse,
    "asset-preview-list-response-v1.schema.json": AssetPreviewListResponse,
    "asset-upload-session-v1.schema.json": UploadSession,
    "asset-validation-report-v1.schema.json": ValidationReport,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        path = OUT / name
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(path)


if __name__ == "__main__":
    main()
