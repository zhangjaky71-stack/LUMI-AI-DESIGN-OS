from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lumi_model_gateway.registry import ModelLifecycle, ModelRecord

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 16, tzinfo=UTC)


def test_model_without_capability_evidence_cannot_become_provider_model() -> None:
    record = ModelRecord(
        model_key="test:no-evidence",
        provider="test",
        model="no-evidence",
        lifecycle=ModelLifecycle.STABLE,
        route_eligible=False,
        observed_at=NOW,
        source_refs=("test-source",),
        claims=(),
        revision_id="revision:no-evidence",
    )
    try:
        record.to_provider_model(registry_snapshot_id="registry:test")
    except ValueError as exc:
        assert "no executable capability claims" in str(exc)
    else:
        raise AssertionError("model without evidence received a synthetic capability")


def test_pricing_region_database_identity_is_total_not_nullable() -> None:
    sql = (
        ROOT
        / "apps/api/migrations/versions/20260816_0007_sql/up_01.sql"
    ).read_text(encoding="utf-8")
    assert "region VARCHAR(64) DEFAULT 'global' NOT NULL" in sql
    assert "UNIQUE (model_revision_id, metric, unit, effective_from, region)" in sql
