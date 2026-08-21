#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL_PROBE = ROOT / "apps/worker-media/src/lumi_worker_media/video_final_probe_runtime.py"
HOSTED_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py"
FINAL_PROBE_TEST = ROOT / "apps/worker-media/tests/test_video_final_probe_runtime.py"
SANDBOX_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_sandbox_runtime.py"
VIDEO_WORKFLOW = ROOT / ".github/workflows/video-generation.yml"
FINAL_WORKFLOW = ROOT / ".github/workflows/final-acceptance-gate.yml"
SELF_PATH = "scripts/validate_video_final_probe_binding.py"


class VideoFinalProbeContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VideoFinalProbeContractError(message)


def read(path: Path) -> str:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require_markers(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    require(not missing, f"{label} missing markers: {missing}")


def main() -> int:
    final_probe = read(FINAL_PROBE)
    hosted = read(HOSTED_RUNTIME)
    tests = read(FINAL_PROBE_TEST)
    sandbox = read(SANDBOX_RUNTIME)
    workflow = read(VIDEO_WORKFLOW)
    final = read(FINAL_WORKFLOW)

    require_markers(
        final_probe,
        (
            "class HostedVerifiedVideoMediaSandbox",
            "await self.renderer.render(timeline)",
            "await self._probe_durable(rendered)",
            "generated/video/v1/",
            "sandbox-exchange/v1/",
            '"ffprobe"',
            '"/sandbox/input/final.mp4"',
            "_decode_ffprobe(stdout)",
            "VIDEO_FINAL_DURABLE_IDENTITY_MISMATCH",
            "VIDEO_FINAL_PROBE_STAGE_IDENTITY_MISMATCH",
            "VIDEO_FINAL_CONTAINER_UNSUPPORTED",
            "VIDEO_FINAL_CODEC_MISMATCH",
            "VIDEO_FINAL_RESOLUTION_MISMATCH",
            "VIDEO_FINAL_FPS_MISMATCH",
            "VIDEO_FINAL_DURATION_MISMATCH",
            "VIDEO_FINAL_UNEXPECTED_AUDIO",
            "replace(rendered.video",
            "duration_ms=int(probe.duration_seconds * Decimal(\"1000\"))",
        ),
        "Hosted final durable probe",
    )
    require(
        final_probe.find("await self._probe_durable(rendered)")
        < final_probe.find("return _verified_final_render(rendered, timeline, probe)"),
        "final durable ffprobe must precede verified metadata return",
    )

    # The lower-level bridge is allowed to carry expected timeline metadata only as
    # an intermediate transport object. The Hosted composition must never feed that
    # object directly into NODE-48 final validation.
    require_markers(
        sandbox,
        (
            "duration_ms = int(duration_seconds * Decimal(\"1000\"))",
            "width=timeline.output_spec.width",
            "height=timeline.output_spec.height",
        ),
        "Sandbox intermediate expected metadata",
    )
    require_markers(
        hosted,
        (
            "HostedVerifiedVideoMediaSandbox",
            "base_sandbox = HostedVideoMediaSandbox.from_spec(spec)",
            "sandbox = HostedVerifiedVideoMediaSandbox(",
            "renderer=base_sandbox",
            "probe_adapter=output",
            "sandbox=TimedMediaSandbox(",
        ),
        "Hosted video final-probe composition",
    )
    require(
        hosted.find("sandbox = HostedVerifiedVideoMediaSandbox(")
        < hosted.find("sandbox=TimedMediaSandbox("),
        "TimedMediaSandbox must wrap the verified final-probe sandbox",
    )

    require_markers(
        tests,
        (
            "test_final_render_is_reprobed_and_expected_metadata_is_not_trusted",
            "assert rendered.video.width == 1",
            "assert verified.video.width == 1280",
            "assert verified.video.duration_ms == 4000",
            "test_final_render_fps_mismatch_fails_before_artifact",
            "VIDEO_FINAL_FPS_MISMATCH",
            "test_final_render_unexpected_audio_fails_before_artifact",
            "VIDEO_FINAL_UNEXPECTED_AUDIO",
            "test_final_render_durable_checksum_mismatch_fails_before_ffprobe",
            "VIDEO_FINAL_DURABLE_IDENTITY_MISMATCH",
            "assert called is False",
        ),
        "Hosted final durable probe tests",
    )

    for source, label in (
        (workflow, "Video Generation workflow"),
        (final, "Final Acceptance workflow"),
    ):
        require(
            f"python3 {SELF_PATH}" in source,
            f"{label} does not execute final durable probe contract",
        )
        require(
            f"{SELF_PATH} \\" in source,
            f"{label} does not syntax-gate final durable probe contract",
        )

    print("Hosted video final durable probe contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VideoFinalProbeContractError as exc:
        raise SystemExit(f"Hosted video final durable probe contract failed: {exc}") from exc
