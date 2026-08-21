#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/worker-media/src/lumi_worker_media/app.py"
VIDEO_JOB_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_job_runtime.py"
HOSTED_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py"
OPENAI_VIDEO = ROOT / "services/model-gateway/src/lumi_model_gateway/openai_video_adapter.py"
TEST = ROOT / "apps/worker-media/tests/test_video_job_runtime.py"
MANIFEST = ROOT / "production/runtime-images/manifest-v1.json"
DOC = ROOT / "docs/runtime/VIDEO-GENERATION-V1.md"
VIDEO_JOB_RUNTIME_PATH = "apps/worker-media/src/lumi_worker_media/video_job_runtime.py"


class VideoCancellationContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VideoCancellationContractError(message)


def read(path: Path) -> str:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require_markers(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    require(not missing, f"{label} missing markers: {missing}")


def validate_repo() -> None:
    app = read(APP)
    executor = read(VIDEO_JOB_RUNTIME)
    hosted = read(HOSTED_RUNTIME)
    provider = read(OPENAI_VIDEO)
    tests = read(TEST)
    doc = read(DOC)

    for source, path in (
        (app, APP),
        (executor, VIDEO_JOB_RUNTIME),
        (hosted, HOSTED_RUNTIME),
        (tests, TEST),
    ):
        try:
            compile(source, str(path), "exec")
        except SyntaxError as exc:
            raise VideoCancellationContractError(
                f"{path.relative_to(ROOT)} has invalid Python syntax: {exc}"
            ) from exc

    require_markers(
        app,
        (
            "from .video_job_runtime import execute_video_job",
            "async def _execute_video_generation_job(message: JobMessage) -> JobOutcome:",
            "return await execute_video_job(",
            "runtime=runtime",
        ),
        "video Celery cancellation binding",
    )
    video_start = app.find('name="lumi.jobs.video.render"')
    preview_start = app.find('@celery_app.task(name="lumi.jobs.asset.preview"', video_start)
    require(video_start >= 0 and preview_start > video_start, "video task block boundary missing")
    video_block = app[video_start:preview_start]
    require(
        "execute_job(" not in video_block,
        "video.render must not use generic request-equals-cancelled executor",
    )

    require_markers(
        executor,
        (
            "async def execute_video_job(",
            "cancellation_before_claim = await store.cancellation_requested(message)",
            "return await _reconcile_cancellation(",
            "result = await runtime.execute(message)",
            "if await store.cancellation_requested(message):",
            '"cancellation_pending": True',
            'if status == "CANCELLED":',
            'if status in {"COMPLETED", "PARTIAL"}:',
            'output["cancellation_request_lost_race_to_terminal"] = True',
            'if status == "FAILED":',
            "VIDEO_CANCELLATION_RECONCILIATION_STATE_INVALID",
        ),
        "provider-reconciled video executor",
    )

    require_markers(
        hosted,
        (
            "async def reconcile_cancellation(",
            "Once a video recovery row exists, provider cancellation must be proven",
            '"cancelled_before_provider_recovery": True',
            "job = await pipeline.cancel(",
            "await self._flush_job(",
            'if job.status == "WAITING_EXTERNAL":',
            "return self._external_wait(job)",
        ),
        "Hosted video cancellation reconciliation",
    )
    require(
        hosted.find("job = await pipeline.cancel(")
        < hosted.find("await self._flush_job(", hosted.find("job = await pipeline.cancel(")),
        "provider cancellation result must be flushed before Task resolution",
    )

    require_markers(
        provider,
        (
            "async def cancel(self, provider_request_id: str) -> ModelResult:",
            "OpenAI Videos exposes delete but this adapter does not equate deletion with proven cancellation",
            "ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE",
            "delivery_state=DeliveryState.NOT_ACCEPTED",
        ),
        "OpenAI video cancellation fail-closed boundary",
    )

    require_markers(
        tests,
        (
            "test_video_cancel_request_stays_waiting_when_provider_cancel_is_unproven",
            "assert outcome.state == JobState.WAITING_EXTERNAL",
            'assert outcome.output["cancellation_pending"] is True',
            "test_video_cancel_request_marks_cancelled_only_after_runtime_confirms",
            "assert outcome.state == JobState.CANCELLED",
            "test_provider_terminal_success_wins_race_with_late_cancel_request",
            'assert outcome.output["cancellation_request_lost_race_to_terminal"] is True',
            "test_invalid_video_cancellation_resolution_fails_closed",
        ),
        "video cancellation executable regression",
    )

    try:
        manifest = json.loads(read(MANIFEST))
    except json.JSONDecodeError as exc:
        raise VideoCancellationContractError("runtime manifest is invalid JSON") from exc
    runtimes = manifest.get("runtimes")
    worker = runtimes.get("worker-media") if isinstance(runtimes, dict) else None
    sources = worker.get("source_paths") if isinstance(worker, dict) else None
    require(
        isinstance(sources, list) and VIDEO_JOB_RUNTIME_PATH in sources,
        "worker-media provenance omits provider-reconciled video job runtime",
    )

    require_markers(
        doc,
        (
            "Cancellation is provider-reconciled",
            "cancellation request",
            "WAITING_EXTERNAL",
        ),
        "canonical Video Runtime cancellation semantics",
    )


def main() -> int:
    validate_repo()
    print("Hosted video cancellation reconciliation contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VideoCancellationContractError as exc:
        raise SystemExit(f"Hosted video cancellation contract failed: {exc}") from exc
