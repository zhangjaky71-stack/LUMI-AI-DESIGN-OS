from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "visual-critic" / "src" / "lumi_visual_critic"
API = ROOT / "apps" / "api" / "src" / "lumi_api" / "visual_critic"
REQUIRED_SERVICE = {
    "engine.py",
    "model.py",
    "ports.py",
    "profiles.py",
    "repository.py",
}
REQUIRED_API = {
    "artifact_adapter.py",
    "codec.py",
    "model_gateway_adapter.py",
    "postgres_repository.py",
    "signal_adapters.py",
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
        if path.name == "engine.py":
            assert "QUALITY_HARD_GATE_FAILED" in source
            assert "REVIEW_REQUIRED" in source
            assert "QUALITY_CRITIC_CALIBRATION_MISMATCH" in source

    artifact = parse(API / "artifact_adapter.py")
    assert "get_version(UUID(artifact_version_id))" in artifact
    assert "head_version" not in artifact
    critic = parse(API / "model_gateway_adapter.py")
    assert "Capability.LLM_VISION" in critic
    assert "allow_fallback=False" in critic
    assert '"severity": {"type": "string", "enum": ["INFO", "WARNING", "ERROR"]}' in critic
    assert '"HARD"' not in critic.split("_CRITIC_SCHEMA", 1)[1].split("class ModelGatewayVisualGraderAdapter", 1)[0]
    calibration = parse(API / "postgres_repository.py")
    assert "QUALITY_CALIBRATION_NOT_CURRENT" in calibration
    assert "artifact_version_id" in calibration

    migration = (
        ROOT
        / "apps"
        / "api"
        / "migrations"
        / "versions"
        / "20260818_0019_visual_critic.py"
    )
    assert 'down_revision = "20260817_0018"' in parse(migration)
    sql = migration.with_name("20260818_0019_sql") / "up.sql"
    sql_source = sql.read_text(encoding="utf-8")
    assert "artifact_version_id UUID NOT NULL REFERENCES artifact_versions" in sql_source
    assert "quality_grader_calibrations" in sql_source
    assert "quality_profile_snapshots" in sql_source
    assert "ck_quality_hard_blocks" in sql_source

    profiles = parse(SERVICE / "profiles.py")
    for key in (
        "EXPLORATION",
        "PRODUCTION_WEB",
        "BRAND_STRICT",
        "PRODUCT_STRICT",
        "PRINT",
        "SOCIAL_FAST",
    ):
        assert f"QualityProfileKey.{key}" in profiles

    print("NODE50_VISUAL_CRITIC_VALIDATION_PASS")


if __name__ == "__main__":
    main()
