from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SPEC_PATH = Path("fixtures/constraints/node-39-benchmark-spec.json")
DEFAULT_OUTPUT = Path("reports/nodes/NODE-39/benchmark-corpus.json")


def build_corpus(spec: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = spec["profiles"]
    rows: list[dict[str, Any]] = []
    for index in range(int(profiles["structure_lock_cases"])):
        rows.append(
            {
                "id": f"structure-{index:03d}",
                "family": "structure_lock",
                "constraint_type": [
                    "LOCK_POSITION",
                    "LOCK_SIZE",
                    "LOCK_ROTATION",
                    "LOCK_PARENT",
                    "LOCK_TEXT",
                ][index % 5],
                "expected": "DENY" if index % 3 else "ALLOW",
            }
        )
    for index in range(int(profiles["qr_variants"])):
        rows.append(
            {
                "id": f"qr-{index:03d}",
                "family": "qr",
                "variant": ["valid", "payload_changed", "missing", "small_quiet_zone"][index % 4],
                "expected": ["PASS", "FAIL", "FAIL", "REPAIR"][index % 4],
            }
        )
    for index in range(int(profiles["protected_region_edits"])):
        rows.append(
            {
                "id": f"region-{index:03d}",
                "family": "protected_region",
                "variant": ["unchanged", "jpeg_compression", "edge_change", "color_change"][index % 4],
                "expected": ["PASS", "PASS", "FAIL", "FAIL"][index % 4],
            }
        )
    for index in range(int(profiles["identity_cases"])):
        rows.append(
            {
                "id": f"identity-{index:03d}",
                "family": "identity_adapter",
                "variant": ["same_product", "wrong_sku", "same_logo", "distorted_logo", "unavailable"][index % 5],
                "expected": ["PASS", "FAIL", "PASS", "FAIL", "FAIL"][index % 5],
            }
        )
    for index in range(int(profiles["compression_false_positive_cases"])):
        rows.append(
            {
                "id": f"compression-{index:03d}",
                "family": "compression_false_positive",
                "quality": 80 + index % 20,
                "expected": "PASS",
            }
        )
    return rows


def validate_corpus(spec: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    profiles = spec["profiles"]
    expected_total = sum(int(value) for value in profiles.values())
    if len(rows) != expected_total:
        raise SystemExit(f"expected {expected_total} rows; got {len(rows)}")
    expected_families = {
        "structure_lock": int(profiles["structure_lock_cases"]),
        "qr": int(profiles["qr_variants"]),
        "protected_region": int(profiles["protected_region_edits"]),
        "identity_adapter": int(profiles["identity_cases"]),
        "compression_false_positive": int(profiles["compression_false_positive_cases"]),
    }
    for family, expected in expected_families.items():
        actual = sum(row["family"] == family for row in rows)
        if actual != expected:
            raise SystemExit(f"{family}: expected {expected}, got {actual}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    spec = json.loads(SPEC_PATH.read_text())
    rows = build_corpus(spec)
    validate_corpus(spec, rows)
    if not args.check:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"spec": spec, "cases": rows}, indent=2) + "\n")
    print(json.dumps({"cases": len(rows), "status": "valid"}, sort_keys=True))


if __name__ == "__main__":
    main()
