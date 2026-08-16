from __future__ import annotations

import ast
import json
from pathlib import Path

from lumi_api.constraints.registry import EVALUATOR_CONTRACTS

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "apps" / "api" / "src" / "lumi_api" / "constraints"
BENCHMARK = ROOT / "benchmarks" / "constraints" / "constraint-following-v1.jsonl"

FORBIDDEN_IMPORT_PREFIXES = (
    "PIL",
    "cv2",
    "pyzbar",
    "qrcode",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "langgraph",
    "langchain",
    "openai",
    "anthropic",
    "boto3",
    "redis",
    "celery",
)

EXPECTED_TYPES = {
    "LOCK_POSITION",
    "LOCK_SIZE",
    "LOCK_ROTATION",
    "LOCK_TRANSFORM",
    "LOCK_ASPECT_RATIO",
    "LOCK_LAYER_ORDER",
    "LOCK_PARENT",
    "LOCK_CONTENT",
    "LOCK_TEXT",
    "LOCK_ASSET",
    "LOCK_IDENTITY",
    "LOCK_STYLE",
    "LOCK_BRAND",
    "PROTECT_REGION",
    "MUST_STAY_INSIDE",
    "MUST_NOT_OVERLAP",
    "MIN_MARGIN",
    "SAFE_AREA",
    "REQUIRE_CONTRAST",
    "REQUIRE_SCANNABILITY",
    "REQUIRE_TEXT_READABILITY",
    "REQUIRE_BRAND_COMPLIANCE",
    "REQUIRE_RESOLUTION",
    "REQUIRE_IDENTITY_SCORE",
}


def validate_import_boundaries() -> None:
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    raise SystemExit(
                        f"forbidden Constraint Engine dependency {module!r} in {path}"
                    )


def validate_registry() -> None:
    actual = set(EVALUATOR_CONTRACTS)
    if actual != EXPECTED_TYPES:
        missing = sorted(EXPECTED_TYPES - actual)
        extra = sorted(actual - EXPECTED_TYPES)
        raise SystemExit(f"evaluator registry mismatch missing={missing} extra={extra}")
    for name, contract in EVALUATOR_CONTRACTS.items():
        if not contract.stages:
            raise SystemExit(f"constraint {name} has no evaluator stage")
        if "postflight" in contract.stages and not contract.postflight_observation_kind:
            raise SystemExit(f"constraint {name} lacks postflight observation contract")


def validate_benchmark() -> None:
    rows = [
        json.loads(line)
        for line in BENCHMARK.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) < 100:
        raise SystemExit(f"constraint benchmark must contain >=100 cases, got {len(rows)}")
    ids = [row["case_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("constraint benchmark case_id values must be unique")
    required = {"only_background", "keep_product", "keep_logo", "keep_qr", "title_size"}
    categories = {row["category"] for row in rows}
    if not required.issubset(categories):
        raise SystemExit(f"benchmark missing categories: {sorted(required - categories)}")
    allowed = {"ALLOW", "ALLOW_WITH_WARNINGS", "DENY", "PASS", "FAIL_HARD"}
    for row in rows:
        if row["expected"] not in allowed:
            raise SystemExit(f"unsupported benchmark expected value in {row['case_id']}")


def main() -> None:
    validate_import_boundaries()
    validate_registry()
    validate_benchmark()
    print("NODE14_CONSTRAINT_ENGINE_VALIDATION_PASS")
    print(f"constraint_types={len(EVALUATOR_CONTRACTS)}")
    print("benchmark_cases>=100")


if __name__ == "__main__":
    main()
