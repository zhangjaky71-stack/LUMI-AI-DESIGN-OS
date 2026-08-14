from __future__ import annotations

import json
import time
from decimal import Decimal
from statistics import median

from lumi_image_edit.mask import NormalizedRect, normalized_to_pixels
from lumi_image_edit.model import EditIntent, ImageEditSpec, SourceImageRef
from lumi_image_edit.planner import plan_edit

ORG = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * fraction)]


def build(index: int) -> ImageEditSpec:
    source = SourceImageRef(
        organization_id=ORG,
        project_id=PROJECT,
        artifact_id="artifact-bench",
        artifact_version_id="version-bench",
        asset_id="asset-bench",
        asset_version="v1",
        durable_ref="asset:bench@v1",
        checksum_sha256="a" * 64,
        width=2048,
        height=2048,
        mime_type="image/png",
        rights="USER_OWNED",
        commercial_use_allowed=True,
    )
    return ImageEditSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=f"00000000-0000-0000-0000-{index + 1:012d}",
        source=source,
        intent=EditIntent(action="RESIZE_TEXT", instruction="resize title", selected_node_ids=("title",), value={"width":600,"height":120}),
        constraints=(),
        protected_regions=(),
        mask=None,
        brand_rule_set_version=None,
        identity_requirement_ids=(),
        budget_limit_usd=Decimal("0"),
        code_git_sha="b" * 40,
        design_document_id="doc-bench",
        design_document_version=3,
        selected_node_kind="TEXT",
    )


def main() -> None:
    durations: list[float] = []
    checksum = 0
    iterations = 5000
    for index in range(iterations):
        spec = build(index)
        started = time.perf_counter()
        rect = normalized_to_pixels(NormalizedRect(0.1, 0.1, 0.8, 0.8), source_width := spec.source.width, source_height := spec.source.height)
        plan = plan_edit(spec)
        checksum ^= hash((plan.route, rect.x, rect.y, rect.width, rect.height, source_width, source_height, spec.semantic_hash))
        durations.append((time.perf_counter() - started) * 1000)
    report = {
        "benchmark": "NODE-47 dependency-free edit planning/mask-coordinate core",
        "iterations": iterations,
        "median_ms": round(median(durations), 4),
        "p95_ms": round(percentile(durations, 0.95), 4),
        "max_ms": round(max(durations), 4),
        "checksum_nonzero": checksum != 0,
        "note": "Excludes provider inference, visual diff, OCR, QR, Identity, storage and PostgreSQL; no live edit-quality SLO is inferred.",
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
