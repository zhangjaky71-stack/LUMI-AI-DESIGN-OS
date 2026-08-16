from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_STATES = {
    "unknown",
    "healthy",
    "degraded",
    "open_circuit",
    "recovering",
    "disabled",
}
EXPECTED_GAPS = {
    "HEALTH-REDIS-001",
    "HEALTH-PROBE-002",
    "HEALTH-ADMIN-003",
    "HEALTH-OBS-004",
    "HEALTH-TUNING-005",
    "HEALTH-PACKAGE-006",
    "HEALTH-CI-007",
}
PYTHON_SCOPE = (
    "services/model-gateway/src/lumi_model_gateway/provider_health.py",
    "services/model-gateway/src/lumi_model_gateway/provider_health_store.py",
    "services/model-gateway/src/lumi_model_gateway/provider_health_postgres.py",
    "services/model-gateway/src/lumi_model_gateway/synthetic_probe.py",
    "services/model-gateway/src/lumi_model_gateway/gateway.py",
    "services/model-gateway/src/lumi_model_gateway/routing.py",
    "services/model-gateway/src/lumi_model_gateway/ports.py",
    "services/model-gateway/src/lumi_model_gateway/memory.py",
    "services/model-gateway/tests/test_provider_health.py",
    "services/model-gateway/tests/test_provider_health_gateway.py",
    "services/model-gateway/tests/test_synthetic_probe.py",
    "apps/api/src/lumi_api/persistence/models_provider_health.py",
    "tools/node24/test_provider_health_redis.py",
    "tools/node24/test_provider_health_database.py",
    "tools/node24/export_health_schemas.py",
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require_python_parses() -> None:
    for relative in PYTHON_SCOPE:
        ast.parse(read(relative), filename=relative)


def require_exact_states() -> None:
    from lumi_model_gateway.provider_health import ProviderHealthState

    states = {item.value for item in ProviderHealthState}
    if states != EXPECTED_STATES:
        raise AssertionError(
            f"ProviderHealthState drifted: {sorted(states)}"
        )


def require_soft_state_boundaries() -> None:
    source = read(
        "services/model-gateway/src/"
        "lumi_model_gateway/provider_health_store.py"
    )
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(
                alias.name.split(".")[0]
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    if "redis" in imported_roots:
        raise AssertionError(
            "core Redis store must use injected client, not hard dependency"
        )
    if "asyncpg" in imported_roots:
        raise AssertionError(
            "core health store must not import asyncpg"
        )
    if "RedisHealthStateStore" not in source:
        raise AssertionError("Redis health store missing")
    if "MemoryHealthStateStore" not in source:
        raise AssertionError("memory health reference store missing")


def require_gateway_integration() -> None:
    gateway = read(
        "services/model-gateway/src/lumi_model_gateway/gateway.py"
    )
    routing = read(
        "services/model-gateway/src/lumi_model_gateway/routing.py"
    )
    errors = read(
        "services/model-gateway/src/lumi_model_gateway/errors.py"
    )
    for marker in (
        "acquire_probe(",
        "release_probe(",
        "record_failure(",
        "record_queue_completion(",
        "record_all_candidates_unavailable(",
    ):
        if marker not in gateway:
            raise AssertionError(f"Gateway health marker missing: {marker}")
    if "request.capability.value" not in routing:
        raise AssertionError(
            "Router health query is not capability scoped"
        )
    if "MODEL_CAPABILITY_TEMPORARILY_UNAVAILABLE" not in errors:
        raise AssertionError(
            "explicit all-candidates-unavailable error missing"
        )


def require_failure_attribution() -> None:
    source = read(
        "services/model-gateway/src/"
        "lumi_model_gateway/provider_health.py"
    )
    for required in (
        '"rate_limit"',
        '"timeout"',
        '"provider_5xx"',
        '"capability_temp_unavailable"',
        '"auth_error"',
        '"provider_unavailable"',
    ):
        if required not in source:
            raise AssertionError(
                f"provider-attributable category missing: {required}"
            )
    for excluded in (
        "invalid_request",
        "user_content_policy_block",
        "budget_exceeded",
        "hard_constraint_invalid",
    ):
        if excluded in source.split("_PROVIDER_ATTRIBUTABLE", 1)[1].split(
            "_PROVIDER_WIDE",
            1,
        )[0]:
            raise AssertionError(
                f"local/user failure polluted health attribution: {excluded}"
            )


def require_probe_fail_safe() -> None:
    from lumi_model_gateway.synthetic_probe import SyntheticProbePolicy

    policy = SyntheticProbePolicy()
    if policy.enabled:
        raise AssertionError("synthetic probes must be disabled by default")
    if policy.allow_paid_probes:
        raise AssertionError("paid synthetic probes must be opt-in")
    if str(policy.max_estimated_cost_usd) != "0":
        raise AssertionError(
            "default synthetic probe cost limit must be zero"
        )
    source = read(
        "services/model-gateway/src/lumi_model_gateway/synthetic_probe.py"
    )
    for marker in (
        "provider_terms_allowed",
        "side_effect_free",
        "probe_internal_error",
        "ProviderCallError",
    ):
        if marker not in source:
            raise AssertionError(
                f"synthetic probe fail-safe marker missing: {marker}"
            )


def require_migration() -> None:
    migration = read(
        "apps/api/migrations/versions/"
        "20260816_0008_provider_health.py"
    )
    if 'revision = "20260816_0008"' not in migration:
        raise AssertionError("NODE-24 migration revision mismatch")
    if 'down_revision = "20260816_0007"' not in migration:
        raise AssertionError("NODE-24 migration base mismatch")
    up = read(
        "apps/api/migrations/versions/"
        "20260816_0008_sql/up_01.sql"
    ) + read(
        "apps/api/migrations/versions/"
        "20260816_0008_sql/up_02.sql"
    )
    for marker in (
        "provider_health_summaries",
        "provider_health_override_audit",
        "trg_provider_health_override_audit_immutable",
        "GRANT SELECT, INSERT",
        "REVOKE UPDATE, DELETE",
    ):
        if marker not in up:
            raise AssertionError(
                f"NODE-24 migration marker missing: {marker}"
            )
    models = read(
        "apps/api/src/lumi_api/persistence/models.py"
    )
    if "_models_provider_health" not in models:
        raise AssertionError(
            "provider health ORM metadata registration missing"
        )


def require_metrics_contract() -> None:
    runtime_doc = read(
        "docs/runtime/PROVIDER-HEALTH-V1.md"
    )
    for metric in (
        "provider_success_rate",
        "provider_p95_latency",
        "provider_429_rate",
        "provider_circuit_state",
        "fallback_rate",
        "all_candidates_unavailable_total",
    ):
        if metric not in runtime_doc:
            raise AssertionError(
                f"provider health metric contract missing: {metric}"
            )


def require_gap_ledger() -> None:
    payload = json.loads(
        read("reports/nodes/NODE-24/gap-ledger.json")
    )
    ids = {item["id"] for item in payload["gaps"]}
    if ids != EXPECTED_GAPS:
        raise AssertionError(
            f"NODE-24 gap ledger drifted: {sorted(ids)}"
        )


def main() -> None:
    require_python_parses()
    require_exact_states()
    require_soft_state_boundaries()
    require_gateway_integration()
    require_failure_attribution()
    require_probe_fail_safe()
    require_migration()
    require_metrics_contract()
    require_gap_ledger()
    print("NODE24_PROVIDER_HEALTH_STATIC_VALID")


if __name__ == "__main__":
    main()
