from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = "services/image-generation/src/lumi_image_generation"
REQUIRED_SERVICE = (
    f"{SERVICE}/model.py",
    f"{SERVICE}/ports.py",
    f"{SERVICE}/prompt.py",
    f"{SERVICE}/variants.py",
    f"{SERVICE}/image_validation.py",
    f"{SERVICE}/validation.py",
    f"{SERVICE}/repository.py",
    f"{SERVICE}/pipeline.py",
    f"{SERVICE}/pipeline_support.py",
    f"{SERVICE}/pipeline_execution.py",
    f"{SERVICE}/pipeline_completion.py",
)
REQUIRED_API = (
    "apps/api/src/lumi_api/image_generation/application.py",
    "apps/api/src/lumi_api/image_generation/model_gateway_adapter.py",
    "apps/api/src/lumi_api/image_generation/node45_reference_adapter.py",
    "apps/api/src/lumi_api/image_generation/artifact_adapter.py",
    "apps/api/src/lumi_api/image_generation/postgres_repository.py",
    "apps/api/src/lumi_api/image_generation/postgres_codec.py",
    "apps/api/src/lumi_api/image_generation/postgres_job_write.py",
    "apps/api/src/lumi_api/api/v1/image_generation_routes.py",
    "apps/api/src/lumi_api/api/v1/image_generation_schemas.py",
    "apps/api/src/lumi_api/persistence/models_image_generation.py",
)
ENDPOINTS = (
    "/projects/{project_id}/image-generations",
    "/image-generations/{generation_id}",
    "/image-generations/{generation_id}/cancel",
)
MODES = (
    "TEXT_TO_IMAGE",
    "REFERENCE_TO_IMAGE",
    "PRODUCT_SCENE",
    "STYLE_REFERENCE",
    "TRANSPARENT_ASSET",
    "BACKGROUND_GENERATION",
    "COMPOSITION_EXPLORATION",
)


def _read(path: str) -> str:
    target = ROOT / path
    assert target.exists(), path
    return target.read_text(encoding="utf-8")


def main() -> None:
    for path in REQUIRED_SERVICE + REQUIRED_API:
        ast.parse(_read(path), filename=path)

    model = _read(f"{SERVICE}/model.py")
    pipeline = "\n".join(
        _read(f"{SERVICE}/{name}")
        for name in (
            "pipeline.py",
            "pipeline_support.py",
            "pipeline_execution.py",
            "pipeline_completion.py",
        )
    )
    gateway = _read("apps/api/src/lumi_api/image_generation/model_gateway_adapter.py")
    refs = _read("apps/api/src/lumi_api/image_generation/node45_reference_adapter.py")
    artifact = _read("apps/api/src/lumi_api/image_generation/artifact_adapter.py")
    pg = "\n".join(
        _read(f"apps/api/src/lumi_api/image_generation/{name}")
        for name in ("postgres_repository.py", "postgres_codec.py", "postgres_job_write.py")
    )
    db_models = _read("apps/api/src/lumi_api/persistence/models_image_generation.py")
    routes = _read("apps/api/src/lumi_api/api/v1/image_generation_routes.py")
    migration = _read("apps/api/migrations/versions/20260817_0015_sql/up.sql")
    wrapper = _read("apps/api/migrations/versions/20260817_0015_image_generation.py")

    assert 'down_revision = "20260817_0014"' in wrapper
    for mode in MODES:
        assert mode in model
    assert "Capability.IMAGE_EDIT" not in gateway
    assert "Capability.IMAGE_MASK_EDIT" not in gateway
    assert "Capability.IMAGE_REFERENCE_CONSISTENCY" in gateway
    assert "await self.gateway.invoke" in gateway
    assert "await self.gateway.get_async_status" in gateway
    assert "GENERATION_POLL_DEFERRED" in pipeline
    assert "GENERATION_RESOLVER_REFERENCE_CONFIRMATION_REQUIRED" in refs
    assert "commercial_use=None" in artifact
    assert "RightsReviewStatus.UNREVIEWED" in artifact
    assert "mark_ready" in artifact
    assert "approve_version" not in artifact
    assert "NODE27_MODEL_GATEWAY_SETTLEMENT" in migration
    assert "audit projection only" in migration
    assert "enforce_image_generation_tenant_scope" in migration
    assert "image_generation_pending" in migration
    assert "OperationSemanticConflict" in pg
    assert "semantic_hash" in pg
    assert "BigInteger" in db_models and "size_bytes" in db_models
    assert 'ForeignKey("artifacts.id"' in db_models
    assert 'ForeignKey("artifact_versions.id"' in db_models
    assert 'server_default=text("now()")' in db_models
    for endpoint in ENDPOINTS:
        assert endpoint in routes, endpoint
    assert "status_code=status.HTTP_202_ACCEPTED" in routes

    gap = json.loads(_read("reports/nodes/NODE-46/gap-ledger.json"))
    assert gap["node"] == "NODE-46"
    assert len(gap["gaps"]) == 5

    fixtures = json.loads(_read("evals/node46/image-generation-fixtures.json"))
    assert fixtures["schema_version"] == "lumi.image-generation-eval/1.0"
    assert len(fixtures["cases"]) == 7

    print("NODE46_IMAGE_GENERATION_VALIDATION_PASS")
    print(f"generation_modes={len(MODES)}")
    print(f"required_endpoints={len(ENDPOINTS)}")
    print(f"fixture_cases={len(fixtures['cases'])}")
    print(f"production_gaps={len(gap['gaps'])}")


if __name__ == "__main__":
    main()
