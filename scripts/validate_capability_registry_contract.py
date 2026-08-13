from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-23 contract marker: {needle}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-23 marker: {needle}")


def validate_seed_manifest() -> None:
    seed_path = ROOT / "config/model-registry/registry.seed.v1.yaml"
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    if seed["schema"] != "lumi.model-registry.seed.v1":
        raise SystemExit("registry seed schema mismatch")
    if int(seed["registry_version"]) != 1:
        raise SystemExit("registry seed version mismatch")
    if len(seed["provider_files"]) != 5:
        raise SystemExit("registry seed must point at all five NODE-07 providers")
    manifest = json.loads(
        (ROOT / str(seed["source_manifest"])).read_text(encoding="utf-8")
    )
    if manifest["expected_counts"]["models"] != 28:
        raise SystemExit("NODE-07 model count changed unexpectedly")
    if manifest["registry_version"] != seed["source_registry_version"]:
        raise SystemExit("NODE-07/23 source registry version mismatch")


def validate_routing_weights() -> None:
    from lumi_model_gateway import compile_registry_seed

    snapshot = compile_registry_seed(
        ROOT / "config/model-registry/registry.seed.v1.yaml",
        repository_root=ROOT,
    )
    if len(snapshot.models) != 28:
        raise SystemExit("compiled registry must contain 28 NODE-07 models")
    if snapshot.benchmarks:
        raise SystemExit("NODE-07 NOT_MEASURED data must not become fake benchmark rows")
    for profile in snapshot.routing_profiles:
        weights = json.loads(profile.weights_json)
        total = sum((Decimal(str(value)) for value in weights.values()), Decimal("0"))
        if total != Decimal("1.00"):
            raise SystemExit(f"routing weights must sum to 1: {profile.profile}={total}")


def assert_router_has_no_provider_literals() -> None:
    path = ROOT / "services/model-gateway/src/lumi_model_gateway/registry_routing.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    literals = {
        node.value.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for provider in ("openai", "google", "anthropic", "runway", "black-forest-labs"):
        if provider in literals:
            raise SystemExit(f"Registry-aware Router hardcodes provider: {provider}")


def main() -> int:
    validate_seed_manifest()
    require(
        "services/model-gateway/src/lumi_model_gateway/capability_registry.py",
        'FULL = "full"',
        'PARTIAL = "partial"',
        'NONE = "none"',
        'UNKNOWN = "unknown"',
        'VERIFIED_DOCS = "verified_docs"',
        'LIVE_TEST = "live_test"',
        'INFERRED = "inferred"',
        "pricing_at",
        "rank_candidates",
        "organization_policy",
        "MODEL_REGISTRY_VERSION_CONTENT_CONFLICT",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/registry_routing.py",
        "capability_registry.snapshot()",
        "REGISTRY_SNAPSHOT:",
        "REGISTRY_VERSION:",
        "REGISTRY_CAPABILITY_UNKNOWN",
        "REGISTRY_CAPABILITY_PARTIAL",
    )
    require(
        "apps/api/alembic/versions/0010_capability_registry.py",
        "CREATE TABLE model_registry_versions",
        "CREATE TABLE model_registry_models",
        "CREATE TABLE model_capability_claims",
        "CREATE TABLE model_pricing_snapshots",
        "CREATE TABLE model_benchmark_scores",
        "CREATE TABLE model_routing_profiles",
        "CREATE TABLE organization_model_policies",
        "GRANT SELECT ON",
    )
    forbid(
        "services/model-gateway/src/lumi_model_gateway/capability_registry.py",
        "API_KEY",
        "SECRET_KEY",
        "ACCESS_TOKEN",
    )
    assert_router_has_no_provider_literals()
    validate_routing_weights()
    print("NODE-23 capability registry static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
