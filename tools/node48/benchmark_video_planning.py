from __future__ import annotations

import time
from decimal import Decimal

from lumi_video_generation.model import ShotSpec, VideoMode, VideoTaskSpec
from lumi_video_generation.storyboard import compile_storyboard


def main() -> None:
    shots = tuple(
        ShotSpec(
            shot_id=f"shot-{index}",
            duration_seconds=Decimal("2"),
            prompt=f"deterministic benchmark shot {index}",
        )
        for index in range(2000)
    )
    spec = VideoTaskSpec(
        organization_id="benchmark-org",
        project_id="benchmark-project",
        task_id="benchmark-task",
        operation_id="benchmark-operation",
        mode=VideoMode.TEXT_TO_VIDEO,
        width=1280,
        height=720,
        fps=30,
        shots=shots,
    )
    started = time.perf_counter()
    compiled = compile_storyboard(spec)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert len(compiled) == 2000
    assert len({item.paid_operation_id for item in compiled}) == 2000
    print(f"NODE48_VIDEO_PLANNING_BENCHMARK_PASS shots=2000 elapsed_ms={elapsed_ms:.3f}")


if __name__ == "__main__":
    main()
