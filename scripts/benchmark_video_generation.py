from __future__ import annotations

import hashlib
import json
import os
import time
from decimal import Decimal
from statistics import median

from lumi_video_generation.model import ShotSpec, TimelineClip, VideoOutputSpec, VideoTaskSpec, VideoTimeline, timeline_hash
from lumi_video_generation.storyboard import compile_storyboard

ORG = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * fraction)]


def build_spec(index: int, shot_count: int) -> VideoTaskSpec:
    shots = tuple(
        ShotSpec(
            shot_id=f"shot-{shot_index:03d}",
            duration_seconds=Decimal("1"),
            prompt=f"benchmark scene {index} shot {shot_index}",
            camera_motion="static" if shot_index % 2 else None,
        )
        for shot_index in range(1, shot_count + 1)
    )
    return VideoTaskSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=f"00000000-0000-0000-0000-{index + 1:012d}",
        mode="STORYBOARD_MULTI_SHOT",
        prompt="benchmark storyboard",
        duration_seconds=Decimal(shot_count),
        aspect_ratio="16:9",
        width=1600,
        height=900,
        fps=24,
        budget_limit_usd=Decimal("10"),
        code_git_sha="a" * 40,
        shots=shots,
        quality_retry_limit=1,
    )


def main() -> None:
    iterations = int(os.environ.get("LUMI_VIDEO_BENCHMARK_ITERATIONS", "1000"))
    shot_count = int(os.environ.get("LUMI_VIDEO_BENCHMARK_SHOTS", "8"))
    durations_ms: list[float] = []
    digest = hashlib.sha256()
    for index in range(iterations):
        spec = build_spec(index, shot_count)
        started = time.perf_counter()
        storyboard = compile_storyboard(spec)
        timeline = VideoTimeline(
            clips=tuple(
                TimelineClip(
                    shot_id=item.shot.shot_id,
                    artifact_version_id=f"artifact-version-{item.ordinal}",
                    durable_ref=f"asset:benchmark-video:{index}:{item.ordinal}",
                    duration_seconds=item.shot.duration_seconds,
                )
                for item in storyboard.shots
            ),
            overlays=(),
            audio_tracks=(),
            transitions=(),
            output_spec=VideoOutputSpec(width=spec.width, height=spec.height, fps=spec.fps),
        )
        digest.update(storyboard.storyboard_hash.encode())
        digest.update(timeline_hash(timeline).encode())
        durations_ms.append((time.perf_counter() - started) * 1000)

    report = {
        "benchmark": "NODE-48 dependency-free storyboard/timeline planning core",
        "iterations": iterations,
        "shots_per_storyboard": shot_count,
        "total_shots": iterations * shot_count,
        "median_ms": round(median(durations_ms), 4),
        "p95_ms": round(percentile(durations_ms, 0.95), 4),
        "max_ms": round(max(durations_ms), 4),
        "digest": digest.hexdigest(),
        "note": (
            "Excludes provider inference/queue/network time, video upload/download, ffmpeg encoding, "
            "Identity/Brand model validators and PostgreSQL. No production latency SLO is inferred."
        ),
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
