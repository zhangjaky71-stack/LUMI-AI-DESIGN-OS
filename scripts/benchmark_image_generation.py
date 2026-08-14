from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from statistics import median

from lumi_image_generation.model import (
    ImageGenerationSpec,
    OutputRequirements,
)
from lumi_image_generation.pipeline import _candidate_id, _generation_id, _variant_operation_id
from lumi_image_generation.prompt import compile_prompt
from lumi_image_generation.variants import choose_variants

ORG = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * fraction)]


def build_spec(index: int) -> ImageGenerationSpec:
    operation_id = f"00000000-0000-0000-0000-{index + 1:012d}"
    return ImageGenerationSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=operation_id,
        purpose="benchmark orchestration",
        mode="TEXT_TO_IMAGE",
        prompt_compilation_ref="benchmark:prompt:v1",
        objective="Generate a product campaign image",
        content=f"benchmark product {index}",
        visual_direction="minimal editorial",
        aspect_ratio="1:1",
        target_width=1024,
        target_height=1024,
        variant_count=4,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile="BALANCED",
        budget_limit_usd=Decimal("0.04"),
        output_requirements=OutputRequirements(format="PNG"),
        code_git_sha="a" * 40,
        seed=index,
    )


def main() -> None:
    iterations = int(os.environ.get("LUMI_IMAGE_GENERATION_BENCHMARK_ITERATIONS", "5000"))
    durations_ms: list[float] = []
    checksum = 0
    for index in range(iterations):
        spec = build_spec(index)
        started = time.perf_counter()
        prompt = compile_prompt(spec)
        decision = choose_variants(spec, estimated_cost_per_variant_usd=Decimal("0.01"))
        generation_id = _generation_id(spec)
        for variant in range(1, decision.selected_count + 1):
            checksum ^= hash(_candidate_id(generation_id, variant))
            checksum ^= hash(_variant_operation_id(spec.operation_id, variant))
        checksum ^= hash(prompt.prompt_hash)
        durations_ms.append((time.perf_counter() - started) * 1000)

    report = {
        "benchmark": "NODE-46 dependency-free orchestration planning core",
        "iterations": iterations,
        "median_ms": round(median(durations_ms), 4),
        "p95_ms": round(percentile(durations_ms, 0.95), 4),
        "max_ms": round(max(durations_ms), 4),
        "checksum_nonzero": checksum != 0,
        "note": (
            "Excludes provider inference, Model Gateway network latency, object storage, "
            "postflight model validators and PostgreSQL. No production SLO is inferred."
        ),
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
