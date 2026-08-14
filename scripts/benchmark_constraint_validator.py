from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/domain/src"))

from lumi_domain.constraint_validator import guarded_execute  # noqa: E402


def build_document(node_count: int = 2000) -> dict[str, Any]:
    children = [f"node-{index}" for index in range(node_count)]
    nodes: dict[str, Any] = {
        "root": {
            "id": "root",
            "kind": "DOCUMENT_ROOT",
            "parent_id": None,
            "children": children,
            "transform": {"x": 0, "y": 0, "width": 4000, "height": 4000},
        }
    }
    for index, node_id in enumerate(children):
        nodes[node_id] = {
            "id": node_id,
            "kind": "SHAPE",
            "parent_id": "root",
            "children": [],
            "transform": {
                "x": (index % 50) * 70,
                "y": (index // 50) * 70,
                "width": 60,
                "height": 60,
            },
        }
    return {
        "schema_version": "1.0",
        "document_id": "benchmark-doc",
        "unit": "px",
        "root_id": "root",
        "nodes": nodes,
        "resources": {},
        "metadata": {"document_version": 10},
    }


def build_transaction(operation_count: int = 100) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    operations: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    for index in range(operation_count):
        node_id = f"node-{index}"
        operations.append(
            {
                "operation_id": f"move-{index}",
                "type": "MOVE_NODE",
                "target_ids": [node_id],
                "expected_document_version": 10,
                "payload": {"dx": 0.1, "dy": 0.1},
            }
        )
        constraints.append(
            {
                "id": f"lock-{index}",
                "type": "LOCK_POSITION",
                "scope": {"node_ids": [node_id]},
                "severity": "SOFT",
                "source": "PROJECT_RULE",
                "priority": 100,
                "parameters": {},
                "active": True,
                "document_version": 10,
            }
        )
    return operations, constraints


def main() -> None:
    document = build_document()
    operations, constraints = build_transaction()
    samples_ms: list[float] = []
    for _ in range(12):
        started = time.perf_counter()
        result = guarded_execute(document, operations, constraints)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if result["preflight"]["decision"] != "ALLOW_WITH_WARNINGS":
            raise SystemExit("benchmark transaction produced unexpected decision")
        samples_ms.append(elapsed_ms)
    steady = samples_ms[2:]
    report = {
        "node_count": 2000,
        "operation_count": 100,
        "constraint_count": 100,
        "samples": len(steady),
        "median_ms": round(statistics.median(steady), 3),
        "p95_ms": round(sorted(steady)[max(0, int(len(steady) * 0.95) - 1)], 3),
        "note": "Measurement only; NODE-39 does not invent an uncalibrated hard latency threshold.",
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
