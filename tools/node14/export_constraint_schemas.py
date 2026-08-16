from __future__ import annotations

import json
from pathlib import Path

from lumi_api.constraints.models import (
    ConstraintSet,
    ConstraintViolation,
    PostflightObservation,
    PreflightResult,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports" / "nodes" / "NODE-14" / "generated-schemas"

SCHEMAS = {
    "constraint-set-v1.schema.json": ConstraintSet.model_json_schema(),
    "constraint-violation-v1.schema.json": ConstraintViolation.model_json_schema(),
    "postflight-observation-v1.schema.json": PostflightObservation.model_json_schema(),
    "preflight-result-v1.schema.json": PreflightResult.model_json_schema(),
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, schema in SCHEMAS.items():
        path = OUTPUT / name
        path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
