from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_SERVICE = (
    "services/asset-intelligence/src/lumi_asset_intelligence/model.py",
    "services/asset-intelligence/src/lumi_asset_intelligence/repository.py",
    "services/asset-intelligence/src/lumi_asset_intelligence/search.py",
    "services/asset-intelligence/src/lumi_asset_intelligence/service.py",
    "services/asset-intelligence/src/lumi_asset_intelligence/duplicates.py",
)
REQUIRED_API = (
    "apps/api/src/lumi_api/asset_intelligence/postgres_repository.py",
    "apps/api/src/lumi_api/asset_intelligence/node18_catalog.py",
    "apps/api/src/lumi_api/asset_intelligence/node23_adapter.py",
    "apps/api/src/lumi_api/asset_intelligence/identity_adapter.py",
    "apps/api/src/lumi_api/api/v1/asset_intelligence_routes.py",
)
ENDPOINTS = (
    "/asset-intelligence/indexes",
    "/asset-intelligence/indexes/{index_id}/build",
    "/asset-intelligence/indexes/{index_id}/activate",
    "/assets/{asset_id}/intelligence/analyze",
    "/assets/{asset_id}/intelligence",
    "/asset-intelligence/search",
    "/asset-intelligence/resolve",
    "/assets/{asset_id}/duplicates",
    "/assets/{asset_id}/usage-feedback",
)


def _read(path: str) -> str:
    target = ROOT / path
    assert target.exists(), path
    return target.read_text(encoding="utf-8")


def main() -> None:
    for path in REQUIRED_SERVICE + REQUIRED_API:
        ast.parse(_read(path), filename=path)

    api_core = ROOT / "apps/api/src/lumi_api/asset_intelligence"
    forbidden_parallel_core = {
        "contracts.py", "duplicates.py", "metadata.py", "ports.py",
        "repository.py", "search.py", "service.py",
    }
    assert not forbidden_parallel_core.intersection(
        {path.name for path in api_core.glob("*.py")}
    )

    model = _read(REQUIRED_SERVICE[0])
    service = _read(REQUIRED_SERVICE[3])
    search = _read(REQUIRED_SERVICE[2])
    pg = _read(REQUIRED_API[0])
    routes = _read(REQUIRED_API[4])
    migration = _read("apps/api/migrations/versions/20260817_0014_sql/up.sql")
    wrapper = _read("apps/api/migrations/versions/20260817_0014_asset_intelligence.py")

    assert "down_revision = \"20260817_0013\"" in wrapper
    assert "EmbeddingCapability" in model and "registry_version_id" in model
    assert "reserve_index_version" in service
    assert "schedule_asset_analysis" in service and "schedule_index_build" in service
    assert "TRAINING_AUTHORIZATION_REQUIRES_RIGHTS_WORKFLOW" in service
    assert "scoped_candidates" in search
    assert "before any scoring" in search
    assert "JOIN assets live_asset" in pg and "LEFT JOIN asset_rights live_rights" in pg
    assert "ASSET_INDEX_ACTIVE_HEAD_CONFLICT" in pg
    assert "FOR UPDATE" in pg
    assert "asset_intelligence_index_counters" in migration
    assert "uq_asset_intelligence_one_active_per_org" in migration
    assert "lumi_asset_intelligence_scope_guard" in migration
    assert "training_authorization_granted = false" in migration
    for endpoint in ENDPOINTS:
        assert endpoint in routes, endpoint
    assert routes.count("status_code=status.HTTP_202_ACCEPTED") >= 2

    gap = json.loads(_read("reports/nodes/NODE-45/gap-ledger.json"))
    assert gap["node"] == "NODE-45"
    assert len(gap["gaps"]) == 5

    fixtures = json.loads(_read("evals/node45/asset-intelligence-fixtures.json"))
    assert fixtures["schema_version"] == "lumi.asset-intelligence-eval/1.0"
    assert len(fixtures["queries"]) + len(fixtures["duplicates"]) == 9

    print("NODE45_ASSET_INTELLIGENCE_VALIDATION_PASS")
    print(f"required_endpoints={len(ENDPOINTS)}")
    print("fixture_cases=9")
    print(f"production_gaps={len(gap['gaps'])}")


if __name__ == "__main__":
    main()
