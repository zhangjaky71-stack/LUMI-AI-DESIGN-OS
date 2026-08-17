from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = (
    "apps/api/src/lumi_api/identity_engine/contracts.py",
    "apps/api/src/lumi_api/identity_engine/scoring.py",
    "apps/api/src/lumi_api/identity_engine/service.py",
    "apps/api/src/lumi_api/identity_engine/constraint_adapter.py",
    "apps/api/src/lumi_api/identity_engine/node18_asset_policy.py",
    "apps/api/src/lumi_api/identity_engine/node45_adapter.py",
    "apps/api/src/lumi_api/identity_engine/postgres_repository.py",
    "apps/api/src/lumi_api/persistence/models_identity_engine.py",
    "apps/api/migrations/versions/20260817_0013_identity_engine.py",
    "apps/api/migrations/versions/20260817_0013_sql/up.sql",
    "apps/api/src/lumi_api/api/v1/identity_engine_routes.py",
    "apps/api/tests/test_identity_engine_node44.py",
    "evals/node44/identity-benchmark.json",
    "reports/nodes/NODE-44/calibration-report.json",
    "docs/runtime/IDENTITY-ENGINE-V1.md",
    "reports/nodes/NODE-44/gap-ledger.json",
)


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing NODE-44 files: {missing}")
    contracts = (ROOT / "apps/api/src/lumi_api/identity_engine/contracts.py").read_text(
        encoding="utf-8"
    )
    service = (ROOT / "apps/api/src/lumi_api/identity_engine/service.py").read_text(
        encoding="utf-8"
    )
    node18 = (
        ROOT / "apps/api/src/lumi_api/identity_engine/node18_asset_policy.py"
    ).read_text(encoding="utf-8")
    node45 = (ROOT / "apps/api/src/lumi_api/identity_engine/node45_adapter.py").read_text(
        encoding="utf-8"
    )
    migration = (
        ROOT / "apps/api/migrations/versions/20260817_0013_sql/up.sql"
    ).read_text(encoding="utf-8")
    routes = (
        ROOT / "apps/api/src/lumi_api/api/v1/identity_engine_routes.py"
    ).read_text(encoding="utf-8")
    for token in (
        "PRODUCT", "LOGO", "CHARACTER", "FACE", "STYLE_REFERENCE",
        "CalibrationReport", "organization_id: UUID", "IdentityValidationResult",
    ):
        assert token in contracts, token
    for token in (
        "IDENTITY_TARGET_MISSING", "IDENTITY_SIGNALS_UNAVAILABLE",
        "IdentitySeverity.HARD", "IDENTITY_COMPARE_REFERENCE_ASSET_REQUIRED",
    ):
        assert token in service, token
    assert "IDENTITY_REFERENCE_ASSET_TENANT_MISMATCH" in node18
    assert "IDENTITY_FACE_NODE45_PERSISTENT_ANALYSIS_FORBIDDEN" in node45
    assert "identity_version_counters" in migration
    assert "trg_identity_snapshot_immutable" in migration
    assert "trg_identity_scope_tenant_guard" in migration
    assert "organization_id = NEW.organization_id" in migration
    assert "identity_type <> 'FACE'" in migration
    assert "identity_validation_records" in migration
    assert "face_embedding" not in migration.casefold()
    endpoint_count = routes.count("@router.")
    assert endpoint_count == 6, endpoint_count
    fixture = json.loads(
        (ROOT / "evals/node44/identity-benchmark.json").read_text(encoding="utf-8")
    )
    assert len(fixture["cases"]) == 16
    assert {case["identity_type"] for case in fixture["cases"]} == {"LOGO", "PRODUCT"}
    calibration = json.loads(
        (ROOT / "reports/nodes/NODE-44/calibration-report.json").read_text(encoding="utf-8")
    )
    assert len(calibration["reports"]) == 2
    assert {report["identity_type"] for report in calibration["reports"]} == {
        "LOGO", "PRODUCT",
    }
    for report in calibration["reports"]:
        assert report["organization_id"]
        assert report["sample_count"] >= 4
        assert 0 <= report["selected_threshold"] <= 100
        assert report["metrics"]["precision"] >= 0.95
    gaps = json.loads(
        (ROOT / "reports/nodes/NODE-44/gap-ledger.json").read_text(encoding="utf-8")
    )
    assert len(gaps["gaps"]) == 5
    print("NODE44_IDENTITY_ENGINE_VALIDATION_PASS")
    print(f"fixture_cases={len(fixture['cases'])}")
    print(f"calibration_reports={len(calibration['reports'])}")
    print(f"required_endpoints={endpoint_count}")
    print(f"production_gaps={len(gaps['gaps'])}")


if __name__ == "__main__":
    main()
