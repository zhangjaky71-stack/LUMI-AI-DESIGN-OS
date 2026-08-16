from __future__ import annotations

import json
from pathlib import Path

from lumi_model_gateway.registry import CapabilitySupport
from lumi_model_gateway.registry_seed import load_seed_snapshot

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = (
    "services/model-gateway/src/lumi_model_gateway/registry.py",
    "services/model-gateway/src/lumi_model_gateway/registry_seed.py",
    "services/model-gateway/src/lumi_model_gateway/registry_postgres.py",
    "services/model-gateway/src/lumi_model_gateway/routing_profile_evaluator.py",
    "apps/api/src/lumi_api/persistence/models_capability_registry.py",
    "apps/api/migrations/versions/20260816_0007_capability_registry.py",
    "apps/api/migrations/versions/20260816_0007_sql/up_01.sql",
    "apps/api/migrations/versions/20260816_0007_sql/up_02.sql",
    "tools/node23/seed_capability_registry.py",
    "tools/node23/test_registry_database.py",
    "docs/models/CAPABILITY-REGISTRY-V1.md",
    "docs/models/CAPABILITY-REGISTRY-PERSISTENCE-V1.md",
    "reports/nodes/NODE-23/gap-ledger.json",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def validate_required_files() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    require(not missing, f"missing NODE-23 files: {missing}")


def validate_migration_chain() -> None:
    migration = read(
        "apps/api/migrations/versions/20260816_0007_capability_registry.py"
    )
    require('revision = "20260816_0007"' in migration, "NODE-23 revision missing")
    require('down_revision = "20260816_0006"' in migration, "NODE-23 base changed")
    models = read("apps/api/src/lumi_api/persistence/models.py")
    require(
        "_models_capability_registry" in models,
        "capability registry ORM metadata is not registered",
    )


def validate_registry_routing_boundary() -> None:
    routing = read("services/model-gateway/src/lumi_model_gateway/routing.py")
    require(
        "capability_registry.capture_snapshot()" in routing,
        "ModelRouter does not query CapabilityRegistry snapshot",
    )
    require(
        "registry_snapshot_id" in routing,
        "route provenance does not retain registry snapshot identity",
    )
    require(
        "adapter_unavailable" in routing,
        "catalog entries without transport adapters do not fail closed",
    )


def validate_seed_truth() -> None:
    snapshot = load_seed_snapshot(ROOT)
    providers = {record.provider for record in snapshot.models.values()}
    require(len(providers) == 5, f"expected 5 providers, got {len(providers)}")
    require(len(snapshot.models) == 28, f"expected 28 models, got {len(snapshot.models)}")
    require(
        len(snapshot.routing_profiles) == 15,
        f"expected 15 routing profiles, got {len(snapshot.routing_profiles)}",
    )
    require(
        all(not record.benchmarks for record in snapshot.models.values()),
        "NODE-07 NOT_MEASURED records became synthetic benchmark scores",
    )
    require(
        all(
            record.claims or not record.route_eligible
            for record in snapshot.models.values()
        ),
        "route-eligible model has no capability evidence",
    )
    require(
        all(
            not claim.route_eligible
            for record in snapshot.models.values()
            for claim in record.claims
            if claim.support is CapabilitySupport.UNKNOWN
        ),
        "unknown capability claim became route eligible",
    )


def validate_pricing_normalization() -> None:
    config = json.loads(
        (ROOT / "config/model-registry.seed.json").read_text(encoding="utf-8")
    )
    raw_count = 0
    for provider_file in config["provider_files"]:
        payload = json.loads((ROOT / provider_file).read_text(encoding="utf-8"))
        raw_count += sum(
            len(item.get("pricing") or [])
            for item in payload.get("models") or []
        )
    snapshot = load_seed_snapshot(ROOT)
    normalized_count = sum(len(record.prices) for record in snapshot.models.values())
    require(
        normalized_count == raw_count,
        f"pricing normalization loss raw={raw_count} normalized={normalized_count}",
    )
    require(
        all(
            price.source_ref and price.observed_at.tzinfo is not None
            for record in snapshot.models.values()
            for price in record.prices
        ),
        "pricing provenance is incomplete",
    )


def validate_profile_truthfulness() -> None:
    routes = json.loads(
        (ROOT / "docs/models/route-candidates.json").read_text(encoding="utf-8")
    )
    require(
        all(route.get("selected_primary") is None for route in routes["routes"]),
        "seed selected a primary before live benchmark",
    )
    evaluator = read(
        "services/model-gateway/src/lumi_model_gateway/routing_profile_evaluator.py"
    )
    require(
        "insufficient_evidence" in evaluator,
        "profile evaluator does not fail open on missing measurements",
    )


def validate_database_security_markers() -> None:
    global_sql = read(
        "apps/api/migrations/versions/20260816_0007_sql/up_01.sql"
    )
    policy_sql = read(
        "apps/api/migrations/versions/20260816_0007_sql/up_02.sql"
    )
    require(
        "model_registry_versions" in global_sql
        and "model_pricing_snapshots" in global_sql
        and "model_benchmark_scores" in global_sql,
        "registry persistence separation is incomplete",
    )
    require(
        "ENABLE ROW LEVEL SECURITY" in policy_sql
        and "organization_model_policies" in policy_sql,
        "organization model policy RLS missing",
    )
    require(
        "REVOKE INSERT, UPDATE, DELETE" in policy_sql,
        "runtime role can mutate global registry facts",
    )


def validate_gap_ledger() -> None:
    ledger = json.loads(
        (ROOT / "reports/nodes/NODE-23/gap-ledger.json").read_text(encoding="utf-8")
    )
    ids = {item["id"] for item in ledger["gaps"]}
    expected = {
        "REGISTRY-ADAPTER-001",
        "REGISTRY-BENCHMARK-002",
        "REGISTRY-INVALIDATION-003",
        "REGISTRY-ADMIN-004",
        "REGISTRY-DEP-005",
        "REGISTRY-PACKAGE-006",
        "REGISTRY-CI-007",
    }
    require(ids == expected, f"unexpected NODE-23 gap ledger: {sorted(ids)}")


def main() -> None:
    checks = (
        validate_required_files,
        validate_migration_chain,
        validate_registry_routing_boundary,
        validate_seed_truth,
        validate_pricing_normalization,
        validate_profile_truthfulness,
        validate_database_security_markers,
        validate_gap_ledger,
    )
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print(f"NODE23_CAPABILITY_REGISTRY_VALID: {len(checks)} checks")


if __name__ == "__main__":
    main()
