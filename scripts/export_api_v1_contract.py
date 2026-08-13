from __future__ import annotations

import argparse
import json
from pathlib import Path

from lumi_api.api import create_contract_app

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "contracts" / "api" / "openapi-v1.json"


def canonical_openapi() -> str:
    schema = create_contract_app().openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    output = args.output
    expected = canonical_openapi()
    if args.check:
        if not output.exists():
            print(f"missing OpenAPI snapshot: {output}")
            return 1
        actual = output.read_text(encoding="utf-8")
        if actual != expected:
            print(f"OpenAPI snapshot is stale: {output}")
            return 1
        print(f"OpenAPI snapshot is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
