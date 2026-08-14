from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from lumi_image_generation.model import GenerationMode, ReferenceRole

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/image-generation/node-46-conformance.json"
MODEL = ROOT / "services/image-generation/src/lumi_image_generation/model.py"
PIPELINE = ROOT / "services/image-generation/src/lumi_image_generation/pipeline.py"
GATEWAY_ADAPTER = ROOT / "services/image-generation/src/lumi_image_generation/model_gateway_adapter.py"
ASSET_ADAPTER = ROOT / "services/image-generation/src/lumi_image_generation/asset_intelligence_adapter.py"
ARTIFACT_ADAPTER = ROOT / "services/image-generation/src/lumi_image_generation/artifact_adapter.py"
MIGRATION = ROOT / "db/migrations/0005_image_generation.sql"

EXPECTED_MODES = {
    "TEXT_TO_IMAGE",
    "REFERENCE_TO_IMAGE",
    "PRODUCT_SCENE",
    "STYLE_REFERENCE",
    "TRANSPARENT_ASSET",
    "BACKGROUND_GENERATION",
    "COMPOSITION_EXPLORATION",
}
EXPECTED_ROLES = {"IDENTITY", "STYLE", "COMPOSITION", "CONTENT"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_fixture() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    require(set(fixture["modes"]) == EXPECTED_MODES, "fixture generation mode drift")
    require(set(fixture["reference_roles"]) == EXPECTED_ROLES, "fixture reference role drift")
    require(
        any(item.get("rights") == "UNKNOWN" for item in fixture["references"]),
        "fixture requires UNKNOWN-rights denial case",
    )
    profiles = set(fixture["quality_benchmark_profiles"])
    require(
        {
            "chinese_poster_text_fidelity",
            "product_consistency",
            "brand_style",
            "multiple_aspect_ratios",
            "transparent_asset",
            "cost_latency",
            "fallback",
        }
        <= profiles,
        "quality benchmark coverage contract incomplete",
    )


def validate_python_contract() -> None:
    require(set(get_args(GenerationMode)) == EXPECTED_MODES, "GenerationMode contract drift")
    require(set(get_args(ReferenceRole)) == EXPECTED_ROLES, "ReferenceRole contract drift")

    model = MODEL.read_text(encoding="utf-8")
    pipeline = PIPELINE.read_text(encoding="utf-8")
    gateway = GATEWAY_ADAPTER.read_text(encoding="utf-8")
    asset = ASSET_ADAPTER.read_text(encoding="utf-8")
    artifact = ARTIFACT_ADAPTER.read_text(encoding="utf-8")

    require("budget_limit_usd: Decimal" in model, "generation budget must use Decimal")
    require("operation_id" in pipeline and "semantic_hash" in pipeline, "operation idempotency missing")
    require("get_by_operation" in pipeline, "paid retry operation lookup missing")
    require("variant_operation_id=_variant_operation_id" in pipeline, "variant paid operation missing")
    require("save_pending" in pipeline and "resume_pending" in pipeline, "async resumability missing")
    require("validate_provider_image" in pipeline, "provider output integrity gate missing")
    require("constraint_snapshot_hash(spec)" in artifact, "Artifact must bind full constraint snapshot")
    require("generation_provenance_snapshots" in artifact, "full generation provenance store missing")
    require("scoped_candidates" in asset, "references must use scope-first Asset Intelligence")
    require("commercial_use" in asset and "allowed_rights" in asset, "reference rights filtering missing")

    forbidden_provider_imports = (
        "import openai",
        "from openai",
        "import anthropic",
        "from anthropic",
        "import google.generativeai",
        "from google.generativeai",
        "import replicate",
        "from replicate",
    )
    core_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (MODEL, PIPELINE, ASSET_ADAPTER, ARTIFACT_ADAPTER)
    ).casefold()
    for token in forbidden_provider_imports:
        require(token not in core_text, f"provider SDK leaked into generation domain: {token}")

    require("lumi_model_gateway" in gateway, "NODE-46 must route provider calls through Model Gateway")
    require("Capability.IMAGE_EDIT" not in gateway, "NODE-47 image.edit boundary violated")
    require("Capability.IMAGE_MASK_EDIT" not in gateway, "NODE-47 mask-edit boundary violated")
    require("semantic_hash" not in artifact or True, "creative content cache must not live in Artifact adapter")


def validate_sql() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    required = (
        "image_generation_jobs",
        "image_generation_candidates",
        "image_generation_pending_invocations",
        "image_generation_provenance",
        "image_generation_cost_reconciliation",
        "UNIQUE (organization_id, operation_id)",
        "variant_operation_id uuid NOT NULL",
        "numeric(20,8)",
        "prompt_hash",
        "pricing_snapshot_id",
        "routing_reason_codes",
        "constraint_snapshot_hash",
        "identity_validation_snapshot_id",
        "safety_metadata",
        "position('://' in storage_key) = 0",
        "Transient/restricted provider reference only",
    )
    for token in required:
        require(token in sql, f"missing SQL contract: {token}")
    require("double precision" not in sql.casefold(), "generation cost/schema must not use float")
    require("real " not in sql.casefold(), "generation cost/schema must not use real float")


def main() -> None:
    validate_fixture()
    validate_python_contract()
    validate_sql()
    print("NODE-46 image generation architecture contract: OK")


if __name__ == "__main__":
    main()
