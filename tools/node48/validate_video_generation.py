from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "video-generation" / "src" / "lumi_video_generation"
API_VIDEO = ROOT / "apps" / "api" / "src" / "lumi_api" / "video_generation"
PERSISTENCE = (
    ROOT
    / "apps"
    / "api"
    / "src"
    / "lumi_api"
    / "persistence"
    / "models_video_generation.py"
)
REQUIRED_SERVICE = {
    "gateway_contract.py",
    "media_sandbox.py",
    "model.py",
    "output_adapter.py",
    "pipeline.py",
    "ports.py",
    "repository.py",
    "storyboard.py",
    "validation.py",
}
REQUIRED_API = {
    "artifact_adapter.py",
    "codec.py",
    "model_gateway_adapter.py",
    "postgres_repository.py",
}


def _parse(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    return source


def main() -> None:
    present = {path.name for path in SERVICE.glob("*.py")}
    missing = sorted(REQUIRED_SERVICE - present)
    assert not missing, f"missing service runtime files: {missing}"
    assert "model_gateway_adapter.py" not in present

    parsed = 0
    for path in sorted(SERVICE.glob("*.py")):
        source = _parse(path)
        parsed += 1
        assert "lumi_model_gateway" not in source, (
            f"provider dependency leaked into service: {path.name}"
        )
        if path.name == "media_sandbox.py":
            assert "shell=True" not in source
            assert "subprocess" not in source
            assert "FFMPEG_NETWORK_OR_PROTOCOL_INPUT_FORBIDDEN" in source
        if path.name == "pipeline.py":
            assert "WAITING_EXTERNAL" in source
            assert "retry_shot" in source
            assert "CANCEL_REQUESTED" in source
            assert "append_final" in source
            assert "final_artifact_version_id" in source

    api_present = {path.name for path in API_VIDEO.glob("*.py")}
    api_missing = sorted(REQUIRED_API - api_present)
    assert not api_missing, f"missing API adapters: {api_missing}"
    gateway_source = _parse(API_VIDEO / "model_gateway_adapter.py")
    assert "VIDEO_PROVIDER_ASYNC_SUBMIT_REQUIRED" in gateway_source
    assert "get_async_status" in gateway_source
    assert "VideoFeatureRegistry" in gateway_source
    artifact_source = _parse(API_VIDEO / "artifact_adapter.py")
    assert "LineageEdgeType.COMPOSED_FROM" in artifact_source
    assert "ArtifactType.VIDEO" in artifact_source
    repository_source = _parse(API_VIDEO / "postgres_repository.py")
    assert "VideoWebhookDedupeModel" in repository_source
    assert "VideoProviderJobModel" in repository_source
    parsed += len(REQUIRED_API)

    persistence_source = _parse(PERSISTENCE)
    parsed += 1
    assert "VideoGenerationJobModel" in persistence_source
    assert "VideoGenerationClipModel" in persistence_source

    migration = (
        ROOT
        / "apps"
        / "api"
        / "migrations"
        / "versions"
        / "20260817_0017_video_generation.py"
    )
    migration_source = _parse(migration)
    parsed += 1
    assert 'down_revision = "20260817_0016"' in migration_source
    sql = migration.with_name("20260817_0017_sql") / "up.sql"
    sql_source = sql.read_text(encoding="utf-8")
    assert "job_json JSONB NOT NULL" in sql_source
    assert "artifact_version_id UUID REFERENCES artifact_versions" in sql_source
    assert "NODE27_MODEL_GATEWAY_SETTLEMENT" in sql_source

    print(
        "NODE48_VIDEO_GENERATION_VALIDATION_PASS "
        f"ast_files={parsed} service_files={len(present)}"
    )


if __name__ == "__main__":
    main()
