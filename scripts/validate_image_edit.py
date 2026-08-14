from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services/image-edit/src/lumi_image_edit"
PIPELINE = SERVICE / "pipeline.py"
PLANNER = SERVICE / "planner.py"
MASK = SERVICE / "mask.py"
GATEWAY = SERVICE / "model_gateway_adapter.py"
ARTIFACT = SERVICE / "artifact_adapter.py"
ROUTER = ROOT / "services/model-gateway/src/lumi_model_gateway/routing.py"
MIGRATION = ROOT / "db/migrations/0006_image_edit.sql"
FIXTURE = ROOT / "fixtures/image-edit/node-47-golden.json"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> None:
    for path in (PIPELINE, PLANNER, MASK, GATEWAY, ARTIFACT, ROUTER, MIGRATION, FIXTURE):
        require(path.exists(), f"missing NODE-47 evidence: {path}")

    planner = PLANNER.read_text(encoding="utf-8")
    pipeline = PIPELINE.read_text(encoding="utf-8")
    mask = MASK.read_text(encoding="utf-8")
    gateway = GATEWAY.read_text(encoding="utf-8")
    artifact = ARTIFACT.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    sql = MIGRATION.read_text(encoding="utf-8")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    require("STRUCTURAL_IR_EDIT" in planner and "NO_MODEL_REQUIRED" in planner, "structural-first route missing")
    require("assert_no_hard_protected_overlap" in pipeline, "hard protected mask-overlap gate missing")
    require("composite_source_regions" in pipeline, "protected compositing fallback missing")
    require("REPLACE_ASSET" in pipeline, "Canvas replace-asset bridge missing")
    require("IMAGE_MASK_EDIT" in gateway and "IMAGE_EDIT" in gateway, "Model Gateway edit capabilities missing")
    require("IMAGE_REFERENCE_CONSISTENCY" in gateway, "reference preservation capability missing")
    require("required_capabilities" in router and "ADDITIONAL_CAPABILITY_MISMATCH" in router, "router multi-capability gate missing")
    require("advance_branch_head_cas" in artifact, "Artifact branch CAS missing")
    require("advance_branch_head=False" in artifact, "candidate must not move source head before validation")
    require("validation.decision == \"PASS\"" in artifact, "PASS-only head advancement missing")
    require("IMAGE_EDIT_MASK_SOURCE_VERSION_MISMATCH" in (SERVICE / "model.py").read_text(encoding="utf-8"), "mask/source version pin missing")
    require("preview_required" in mask, "high-impact mask preview contract missing")

    require(fixture["case_count"] >= 100, "golden suite must materialize 100+ cases")
    require(sum(item["count"] for item in fixture["templates"]) == fixture["case_count"], "golden suite expansion mismatch")
    categories = {item["category"] for item in fixture["templates"]}
    require({"UNCHANGED_PRODUCT","UNCHANGED_LOGO","UNCHANGED_QR","BACKGROUND_CHANGED","STRUCTURAL_NO_MODEL"} <= categories, "golden acceptance categories missing")
    require(fixture["production_quality_claim"] is False, "synthetic fixture must not claim live provider quality")

    for table in (
        "image_edit_jobs",
        "image_edit_masks",
        "image_edit_protected_regions",
        "image_edit_pending_invocations",
        "image_edit_provenance",
        "image_edit_validation_findings",
    ):
        require(table in sql, f"missing edit table: {table}")
    require("UNIQUE (organization_id, operation_id)" in sql, "edit operation idempotency missing")
    require("result_artifact_version_id <> source_artifact_version_id" in sql, "source overwrite protection missing")
    require("numeric(20,8)" in sql, "edit cost must use numeric")
    require("instruction_hash" in sql and "validation_report_hash" in sql, "provenance audit hashes missing")

    forbidden = ("import openai", "from openai", "import anthropic", "import replicate")
    domain = "\n".join(path.read_text(encoding="utf-8").casefold() for path in SERVICE.glob("*.py"))
    for token in forbidden:
        require(token not in domain, f"provider SDK leaked into Image Edit: {token}")

    print("NODE-47 image edit architecture contract: OK")


if __name__ == "__main__":
    main()
