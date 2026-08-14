from __future__ import annotations

import os
from statistics import median
from time import perf_counter

from lumi_domain.design_ir_runtime import execute_operations

NODE_COUNT = 2_000
OPERATION_COUNT = 100
DEFAULT_BUDGET_MS = 1_500.0


def make_document() -> dict[str, object]:
    children = [f"node-{index}" for index in range(1, NODE_COUNT)]
    nodes: dict[str, object] = {
        "root": {
            "id": "root",
            "kind": "DOCUMENT_ROOT",
            "parent_id": None,
            "children": children,
        }
    }
    for index in range(1, NODE_COUNT):
        nodes[f"node-{index}"] = {
            "id": f"node-{index}",
            "kind": "TEXT",
            "parent_id": "root",
            "children": [],
            "content": f"Node {index}",
            "transform": {"x": index, "y": index, "width": 100, "height": 20},
        }
    return {
        "schema_version": "1.0",
        "document_id": "node-38-benchmark",
        "unit": "px",
        "root_id": "root",
        "nodes": nodes,
        "resources": {},
        "metadata": {"document_version": 0},
    }


def make_operations() -> list[dict[str, object]]:
    return [
        {
            "operation_id": f"move-{index}",
            "type": "MOVE_NODE",
            "target_ids": [f"node-{index + 1}"],
            "expected_document_version": 0,
            "payload": {"dx": 1, "dy": -1},
        }
        for index in range(OPERATION_COUNT)
    ]


def main() -> None:
    document = make_document()
    operations = make_operations()
    samples: list[float] = []
    for _ in range(7):
        started = perf_counter()
        result = execute_operations(document, operations)
        elapsed_ms = (perf_counter() - started) * 1_000
        assert result["ok"] is True
        samples.append(elapsed_ms)

    median_ms = median(samples)
    budget_ms = float(os.environ.get("LUMI_DESIGN_IR_BENCHMARK_BUDGET_MS", DEFAULT_BUDGET_MS))
    print(
        f"NODE-38 benchmark: nodes={NODE_COUNT} operations={OPERATION_COUNT} "
        f"median_ms={median_ms:.2f} budget_ms={budget_ms:.2f}"
    )
    if median_ms > budget_ms:
        raise SystemExit(f"Design IR runtime benchmark exceeded {budget_ms:.2f} ms budget")


if __name__ == "__main__":
    main()
