from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTES = (
    "STRUCTURAL_IR_EDIT",
    "PIXEL_LOCAL_EDIT",
    "REGENERATE_REGION",
    "FULL_IMAGE_EDIT",
    "HYBRID",
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> None:
    common = _read("services/image-edit/src/lumi_image_edit/contracts_common.py")
    planner = _read("services/image-edit/src/lumi_image_edit/planner.py")
    pipeline = _read("services/image-edit/src/lumi_image_edit/pipeline.py")
    support = _read("services/image-edit/src/lumi_image_edit/pipeline_support.py")
    lifecycle = _read("services/image-edit/src/lumi_image_edit/pipeline_lifecycle.py")
    validation = _read("services/image-edit/src/lumi_image_edit/validation.py")
    router = _read("services/model-gateway/src/lumi_model_gateway/routing.py")
    routes = _read("apps/api/src/lumi_api/api/v1/image_edit_routes.py")
    app = _read("apps/api/src/lumi_api/api/v1/app.py")
    models = _read("apps/api/src/lumi_api/persistence/models.py")
    migration = _read("apps/api/migrations/versions/20260817_0016_image_edit.py")
    downgrade = _read("apps/api/migrations/versions/20260817_0016_sql/down.sql")
    workflow = _read(".github/workflows/node-47-image-edit.yml")

    for route in ROUTES:
        assert route in common
    assert "NO_MODEL_REQUIRED" in planner
    assert "IMAGE_EDIT_SOURCE_CHANGED" in support
    assert "IMAGE_EDIT_PROVIDER_SAFETY_BLOCK" in support
    assert "image_edit.mask_approved" in lifecycle
    assert "image_edit.broad_change_confirmed" in lifecycle
    assert "constraint-validator" in validation
    assert "brand-rules-engine" in validation
    assert "required_capabilities" in router
    assert "transport_model_supports" in router
    assert routes.count('@router.') == 5
    assert "image_edit_router" in app
    assert "_models_image_edit" in models
    assert 'revision = "20260817_0016"' in migration
    assert 'down_revision = "20260817_0015"' in migration
    assert "downgrade blocked" in downgrade
    assert "uv sync --all-packages --frozen" in workflow
    assert "ruff check" in workflow
    assert "pyright" in workflow

    corpus = json.loads(_read("evals/node47/local-edit-corpus.json"))
    case_count = int(corpus["cases_per_scenario"]) * len(corpus["scenarios"])
    assert case_count >= 100
    gaps = json.loads(_read("reports/nodes/NODE-47/gap-ledger.json"))
    assert gaps["node"] == "NODE-47"
    assert len(gaps["gaps"]) == 5

    python_roots = (
        "services/image-edit/src",
        "apps/api/src/lumi_api/image_edit",
        "tools/node47",
    )
    parsed = 0
    for relative in python_roots:
        for path in (ROOT / relative).rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"))
            parsed += 1

    print("NODE47_IMAGE_EDIT_VALIDATION_PASS")
    print(f"routes={len(ROUTES)} golden_cases={case_count} production_gaps=5")
    print(f"ast_files={parsed}")


if __name__ == "__main__":
    main()
