from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/brand-rules/src"))

from lumi_brand_rules import (  # noqa: E402
    BrandAssetSet,
    BrandRule,
    BrandRuleSet,
    BrandTokenSet,
    evaluate_brand_compliance,
    publish_rule_set,
)


def build_fixture(node_count: int, rule_count: int) -> tuple[dict[str, object], BrandRuleSet, BrandTokenSet, BrandAssetSet]:
    nodes: dict[str, object] = {
        "root": {"id": "root", "kind": "DOCUMENT_ROOT", "children": []},
    }
    children: list[str] = []
    for index in range(node_count):
        node_id = f"node-{index:05d}"
        children.append(node_id)
        nodes[node_id] = {
            "id": node_id,
            "kind": "SHAPE",
            "role": "brand-surface",
            "fill": "#111111" if index % 10 else "#ff0000",
            "metadata": {"spacing": 8},
        }
    nodes["root"] = {"id": "root", "kind": "DOCUMENT_ROOT", "children": children}
    rules = tuple(
        BrandRule(
            id=f"rule-{index:03d}",
            category="COLOR",
            type="FORBIDDEN_COLORS",
            severity="SOFT",
            source="MANUAL_ADMIN",
            priority=index,
            scope={"roles": ["brand-surface"]},
            parameters={"colors": ["#ff0000"]},
        )
        for index in range(rule_count)
    )
    rule_set = publish_rule_set(
        BrandRuleSet(
            id="benchmark-rules",
            organization_id="org-benchmark",
            brand_profile_id="brand-benchmark",
            version="1.0.0",
            status="DRAFT",
            token_set_version="1.0.0",
            asset_set_version="1.0.0",
            rules=rules,
        )
    )
    tokens = BrandTokenSet(
        brand_profile_id="brand-benchmark",
        version="1.0.0",
        colors={"primary": "#111111"},
        font_asset_ids=(),
        spacing_scale=(4, 8, 12, 16),
    )
    assets = BrandAssetSet(
        brand_profile_id="brand-benchmark",
        version="1.0.0",
        logo_asset_ids=(),
        font_asset_ids=(),
        reference_asset_ids=(),
    )
    document = {"metadata": {"document_version": 1}, "nodes": nodes}
    return document, rule_set, tokens, assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, default=2000)
    parser.add_argument("--rules", type=int, default=40)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--max-median-ms", type=float, default=1500.0)
    args = parser.parse_args()

    fixture = build_fixture(args.nodes, args.rules)
    timings: list[float] = []
    diagnostic_count = 0
    for _ in range(args.runs):
        started = time.perf_counter()
        report = evaluate_brand_compliance(*fixture)
        timings.append((time.perf_counter() - started) * 1000)
        diagnostic_count = len(report.diagnostics)
    median_ms = statistics.median(timings)
    print(json.dumps({
        "nodes": args.nodes,
        "rules": args.rules,
        "runs": args.runs,
        "median_ms": round(median_ms, 3),
        "diagnostics": diagnostic_count,
    }, sort_keys=True))
    if median_ms > args.max_median_ms:
        raise SystemExit(
            f"brand benchmark median {median_ms:.2f}ms exceeds {args.max_median_ms:.2f}ms"
        )


if __name__ == "__main__":
    main()
