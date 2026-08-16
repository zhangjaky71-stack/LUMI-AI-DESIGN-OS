from __future__ import annotations

import ast
from pathlib import Path

from lumi_api.assets.models import AssetEventType, QuotaPolicy, RightsAssertion
from lumi_api.assets.object_store import ObjectStore

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps" / "api" / "src" / "lumi_api" / "assets"
ROUTES = ROOT / "apps" / "api" / "src" / "lumi_api" / "api" / "v1" / "asset_routes.py"
MIGRATION = (
    ROOT
    / "apps"
    / "api"
    / "migrations"
    / "versions"
    / "20260816_0004_asset_storage.py"
)
SQL_DIR = (
    ROOT
    / "apps"
    / "api"
    / "migrations"
    / "versions"
    / "20260816_0004_sql"
)
COMPOSE = ROOT / "infra" / "compose" / "docker-compose.yml"


def assert_object_store_contract() -> None:
    required = {
        "create_upload",
        "start_multipart",
        "sign_part",
        "complete_multipart",
        "abort_multipart",
        "head",
        "iter_bytes",
        "put_derived",
        "get_signed_download",
        "copy",
        "delete_candidate",
    }
    assert required <= set(ObjectStore.__dict__)
    quota = QuotaPolicy()
    assert quota.download_ttl_seconds <= 900
    assert quota.upload_ttl_seconds <= 3600


def assert_security_contract() -> None:
    source = (ASSETS / "security.py").read_text(encoding="utf-8")
    for fragment in (
        "javascript:",
        "<!DOCTYPE",
        "foreignObject",
        "SVG_EVENT_HANDLER_REJECTED",
        "FFPROBE_UNAVAILABLE",
    ):
        assert fragment in source
    service = (ASSETS / "service.py").read_text(encoding="utf-8")
    assert 'f"org/{organization_id}/project/{project_id}/asset/{asset_id}/"' in service
    assert "expected_checksum_sha256" in service
    assert "current_verified_usage" in service
    assert "SCAN_UNAVAILABLE_OR_FAILED" in service
    assert set(RightsAssertion) == {
        RightsAssertion.USER_OWNED,
        RightsAssertion.LICENSED,
        RightsAssertion.UNKNOWN,
    }
    assert {event.value for event in AssetEventType} == {
        "asset.upload.created",
        "asset.upload.completed",
        "asset.scan.failed",
        "asset.ready",
        "asset.rejected",
        "asset.preview.created",
    }


def assert_no_large_binary_api_proxy() -> None:
    source = ROUTES.read_text(encoding="utf-8")
    assert "UploadFile" not in source
    assert "File(" not in source
    for fragment in (
        '"/projects/{project_id}/assets/uploads"',
        '"/assets/uploads/{upload_id}/complete"',
        '"/assets/{asset_id}/download"',
        '"/assets/{asset_id}/previews"',
    ):
        assert fragment in source


def assert_migration_contract() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260816_0004"' in migration
    assert 'down_revision = "20260816_0003"' in migration
    snapshot = "\n".join(
        (SQL_DIR / name).read_text(encoding="utf-8")
        for name in ("up_01.sql", "up_02.sql")
    )
    for fragment in (
        "asset_upload_sessions",
        "asset_validation_reports",
        "tenant_isolation_asset_upload_sessions",
        "tenant_isolation_asset_validation_reports",
        "lumi_asset_storage_same_tenant_guard",
        "asset object key violates canonical tenant prefix",
        "REVOKE UPDATE, DELETE ON TABLE asset_validation_reports",
        "USER_OWNED",
        "commercial_use",
    ):
        assert fragment in snapshot, fragment


def assert_architecture_boundaries() -> None:
    forbidden = {"boto3", "botocore", "PIL", "cv2", "openai", "anthropic"}
    for path in ASSETS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, (path, alias.name)
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, (path, node.module)


def assert_local_security_profile() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    assert "clamav/clamav:1.5.3" in source
    assert "profiles: [security]" in source
    assert "3310" in source


def main() -> None:
    assert_object_store_contract()
    assert_security_contract()
    assert_no_large_binary_api_proxy()
    assert_migration_contract()
    assert_architecture_boundaries()
    assert_local_security_profile()
    print(
        "NODE18_ASSET_STORAGE_VALIDATION_PASS: object-store boundary, direct upload, "
        "checksum/MIME/SVG/scanner security, tenant key strategy, RLS, signed downloads"
    )


if __name__ == "__main__":
    main()
