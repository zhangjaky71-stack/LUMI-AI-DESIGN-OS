from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "export-engine" / "src" / "lumi_export_engine"
API = ROOT / "apps" / "api" / "src" / "lumi_api" / "export_engine"
REQUIRED_SERVICE = {
    "model.py",
    "packaging.py",
    "pipeline.py",
    "ports.py",
    "renderers.py",
    "repository.py",
}
REQUIRED_API = {
    "authorization_adapter.py",
    "codec.py",
    "download_adapter.py",
    "postgres_repository.py",
    "queue_adapter.py",
    "snapshot_adapter.py",
}


def parse(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    return source


def main() -> None:
    service_files = {path.name for path in SERVICE.glob("*.py")}
    api_files = {path.name for path in API.glob("*.py")}
    assert not (REQUIRED_SERVICE - service_files), REQUIRED_SERVICE - service_files
    assert not (REQUIRED_API - api_files), REQUIRED_API - api_files

    for path in sorted(SERVICE.glob("*.py")):
        source = parse(path)
        assert "lumi_api" not in source, f"API dependency leaked into {path.name}"
        assert "latest" not in source.lower(), f"latest fallback leaked into {path.name}"

    snapshot = parse(API / "snapshot_adapter.py")
    assert "get_version(UUID(artifact_version_id))" in snapshot
    assert "head_version" not in snapshot
    queue = parse(API / "queue_adapter.py")
    assert 'job_kind="export.package"' in queue
    download = parse(API / "download_adapter.py")
    assert "presign_get" in download

    repository = parse(API / "postgres_repository.py")
    assert "record_grant" in repository
    assert "grant.url" not in repository

    migration = (
        ROOT
        / "apps"
        / "api"
        / "migrations"
        / "versions"
        / "20260817_0018_export_engine.py"
    )
    assert 'down_revision = "20260817_0017"' in parse(migration)
    sql = migration.with_name("20260817_0018_sql") / "up.sql"
    sql_source = sql.read_text(encoding="utf-8")
    grant_section = sql_source.split("CREATE TABLE export_download_grants", 1)[1]
    assert " url " not in grant_section.lower()
    assert " signed" not in grant_section.lower()
    assert "artifact_version_id UUID NOT NULL REFERENCES artifact_versions" in sql_source

    print("NODE49_EXPORT_ENGINE_VALIDATION_PASS")


if __name__ == "__main__":
    main()
