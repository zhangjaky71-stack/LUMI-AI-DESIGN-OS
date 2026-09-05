#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

LOWER_IS_BETTER = ("error_rate", "p50_ms", "p95_ms", "p99_ms", "mean_ms")


def load(path: str) -> dict[str, object]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected JSON object")
    return data


def number(data: dict[str, object], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)):
        raise SystemExit(f"result missing numeric metric: {key}")
    return float(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("current")
    parser.add_argument("--baseline")
    parser.add_argument("--max-regression-pct", type=float, default=15.0)
    parser.add_argument("--p95-target-ms", type=float)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    args = parser.parse_args()
    if not 0 <= args.max_regression_pct <= 1000:
        parser.error("max regression percent must be 0..1000")
    current = load(args.current)
    failures: list[str] = []

    if args.p95_target_ms is not None and number(current, "p95_ms") > args.p95_target_ms:
        failures.append(f"p95_ms {number(current, 'p95_ms'):.3f} > target {args.p95_target_ms:.3f}")
    if number(current, "error_rate") > args.max_error_rate:
        failures.append(f"error_rate {number(current, 'error_rate'):.6f} > {args.max_error_rate:.6f}")

    comparisons: dict[str, dict[str, float]] = {}
    if args.baseline:
        baseline = load(args.baseline)
        if current.get("kind") != baseline.get("kind"):
            failures.append("current/baseline result kinds differ")
        for metric in LOWER_IS_BETTER:
            cur = number(current, metric)
            base = number(baseline, metric)
            pct = 0.0 if base == 0 and cur == 0 else (float("inf") if base == 0 else ((cur - base) / base) * 100)
            comparisons[metric] = {"current": cur, "baseline": base, "regression_pct": pct}
            if pct > args.max_regression_pct:
                failures.append(f"{metric} regression {pct:.2f}% > {args.max_regression_pct:.2f}%")
        cur_rps, base_rps = number(current, "rps"), number(baseline, "rps")
        drop = 0.0 if base_rps == 0 else ((base_rps - cur_rps) / base_rps) * 100
        comparisons["rps"] = {"current": cur_rps, "baseline": base_rps, "regression_pct": drop}
        if drop > args.max_regression_pct:
            failures.append(f"rps regression {drop:.2f}% > {args.max_regression_pct:.2f}%")

    report = {"status": "FAIL" if failures else "PASS", "failures": failures, "comparisons": comparisons}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
