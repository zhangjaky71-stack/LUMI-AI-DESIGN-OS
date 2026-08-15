from __future__ import annotations

import argparse
import json
from pathlib import Path

from lumi_api.design_ir.document import DesignIRDocument
from lumi_api.design_ir.operations import DesignOperationBatch


def write_schema(path: Path, schema: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/nodes/NODE-13/generated-schemas"),
    )
    args = parser.parse_args()

    write_schema(
        args.output_dir / "design-ir-v1.schema.json",
        DesignIRDocument.model_json_schema(),
    )
    write_schema(
        args.output_dir / "design-operation-batch-v1.schema.json",
        DesignOperationBatch.model_json_schema(),
    )
    print(f"wrote Design IR schemas to {args.output_dir}")


if __name__ == "__main__":
    main()
