#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/worker-media/src/lumi_worker_media/app.py"
VIDEO_JOB_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_job_runtime.py"
HOSTED_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py"
PIPELINE = ROOT / "services/video-generation/src/lumi_video_generation/pipeline.py"
OPENAI_VIDEO = ROOT / "services/model-gateway/src/lumi_model_gateway/openai_video_adapter.py"
TEST = ROOT / "apps/worker-media/tests/test_video_job_runtime.py"
HOSTED_TEST = ROOT / "apps/worker-media/tests/test_video_cancellation_runtime.py"
PIPELINE_TEST = ROOT / "services/video-generation/tests/test_video_cancellation.py"
MANIFEST = ROOT / "production/runtime-images/manifest-v1.json"
DOC = ROOT / "docs/runtime/VIDEO-GENERATION-V1.md"
VIDEO_WORKFLOW = ROOT / ".github/workflows/video-generation.yml"
FINAL_WORKFLOW = ROOT / ".github/workflows/final-acceptance-gate.yml"
VIDEO_JOB_RUNTIME_PATH = "apps/worker-media/src/lumi_worker_media/video_job_runtime.py"
SELF_PATH = "scripts/validate_video_cancellation_contract.py"


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
    pipeline = read(PIPELINE)
    provider = read(OPENAI_VIDEO)
    tests = read(TEST)
    hosted_tests = read(HOSTED_TEST)
    pipeline_tests = read(PIPELINE_TEST)
    doc = read(DOC)
    video_workflow = read(VIDEO_WORKFLOW)
    final_workflow = read(FINAL_WORKFLOW)

    for source, path in (
        (app, APP),
        (executor, VIDEO_JOB_RUNTIME),
        (hosted, HOSTED_RUNTIME),
        (pipeline, PIPELINE),
        (tests, TEST),
        (hosted_tests, HOSTED_TEST),
        (pipeline_tests, PIPELINE_TEST),
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
            'if job.status == "WAITING_EXTERNAL":',
            "job = await pipeline.resume(",
            "allow_quality_retry=False",
            "never launch a quality retry or replacement",
            "await self._flush_job(",
            "return self._external_wait(job)",
        ),
        "Hosted video cancellation reconciliation",
    )
    cancellation_start = hosted.find("    async def reconcile_cancellation(")
    build_start = hosted.find("    def _build_pipeline(", cancellation_start)
    require(
        cancellation_start >= 0 and build_start > cancellation_start,
        "Hosted cancellation function boundary missing",
    )
    cancellation_block = hosted[cancellation_start:build_start]
    cancel_at = cancellation_block.find("job = await pipeline.cancel(")
    waiting_at = cancellation_block.find('if job.status == "WAITING_EXTERNAL":', cancel_at)
    resume_at = cancellation_block.find("job = await pipeline.resume(", waiting_at)
    no_retry_at = cancellation_block.find("allow_quality_retry=False", resume_at)
    flush_at = cancellation_block.find("await self._flush_job(", no_retry_at)
    require(
        0 <= cancel_at < waiting_at < resume_at < no_retry_at < flush_at,
        "Hosted cancellation must cancel, reconcile the same provider request without paid quality retry, then flush",
    )
    require(
        cancellation_block.count("await pipeline.resume(") == 1,
        "Hosted cancellation must poll/reconcile at most once per Worker invocation",
    )
    require(
        cancellation_block.count("allow_quality_retry=False") == 1,
        "Hosted cancellation must explicitly suppress replacement paid quality retry",
    )
    require(
        "pipeline.start(" not in cancellation_block
        and "pipeline.submit(" not in cancellation_block,
        "Hosted cancellation must never directly submit replacement paid provider work",
    )
    require(
        cancellation_block.count("await self._flush_job(") == 1,
        "Hosted cancellation must persist one unified cancel/poll result",
    )

    require_markers(
        pipeline,
        (
            "async def resume(",
            "allow_quality_retry: bool = True",
            "allow_quality_retry=allow_quality_retry",
            "async def cancel(self, *, organization_id: str, video_job_id: str) -> VideoJob:",
            "if pending is None:",
            "return job",
            "result = await self.gateway.cancel(pending=pending)",
            "self.repository.save_provider_job(replace(pending, result=result))",
            'if result.status != "CANCELLED":',
            "job = await self._record_cost(job, waiting, result)",
            "self.repository.delete_provider_job(",
            'status="CANCELLED"',
            '"video_generation.cancelled"',
            'if result.status != "CANCELLED" and allow_quality_retry:',
            "if allow_quality_retry:",
        ),
        "provider-neutral cancellation truth",
    )
    pipeline_cancel_start = pipeline.find("    async def cancel(")
    advance_start = pipeline.find("    async def _advance(", pipeline_cancel_start)
    require(
        pipeline_cancel_start >= 0 and advance_start > pipeline_cancel_start,
        "provider-neutral cancellation function boundary missing",
    )
    pipeline_cancel = pipeline[pipeline_cancel_start:advance_start]
    missing_at = pipeline_cancel.find("if pending is None:")
    save_at = pipeline_cancel.find("self.repository.save_provider_job(replace(pending, result=result))")
    status_at = pipeline_cancel.find('if result.status != "CANCELLED":')
    cost_at = pipeline_cancel.find("job = await self._record_cost(job, waiting, result)")
    delete_at = pipeline_cancel.find("self.repository.delete_provider_job(", cost_at)
    cancelled_at = pipeline_cancel.find("cancelled = replace(", delete_at)
    require(
        0 <= missing_at < save_at < status_at < cost_at < delete_at < cancelled_at,
        "provider-neutral cancellation must preserve non-cancel provider truth before terminal cancellation work",
    )
    require(
        pipeline_cancel.find("return job", missing_at) < save_at,
        "missing provider recovery must remain unresolved instead of self-certifying cancellation",
    )
    require(
        pipeline_cancel.find("return job", status_at) < cost_at,
        "PENDING/SUCCEEDED/FAILED cancel results must return before terminal cost/archive",
    )

    resume_start = pipeline.find("    async def resume(")
    cancel_start = pipeline.find("    async def cancel(", resume_start)
    resume_block = pipeline[resume_start:cancel_start]
    require(
        "allow_quality_retry=allow_quality_retry" in resume_block,
        "provider resume must propagate the cancellation no-quality-retry control into terminal reconciliation",
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
    provider_cancel_start = provider.find("    async def cancel(self, provider_request_id: str)")
    stream_start = provider.find("    def stream(", provider_cancel_start)
    require(
        provider_cancel_start >= 0 and stream_start > provider_cancel_start,
        "OpenAI video cancel boundary missing",
    )
    provider_cancel_block = provider[provider_cancel_start:stream_start]
    require(
        'method="DELETE"' not in provider_cancel_block
        and "delete_object" not in provider_cancel_block,
        "OpenAI Hosted video must not equate provider deletion with proven cancellation",
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
        "video cancellation executor regression",
    )
    require_markers(
        hosted_tests,
        (
            "test_unproven_cancel_polls_same_provider_once_before_single_flush",
            'assert pipeline.calls == ["cancel", "resume"]',
            'assert pipeline.resume_allow_quality_retry == [False]',
            'assert [job.status for job in runtime.flushed] == ["COMPLETED"]',
            "test_still_pending_after_cancel_poll_remains_external_wait",
            'assert [job.status for job in runtime.flushed] == ["WAITING_EXTERNAL"]',
            "test_failed_provider_truth_does_not_enable_quality_retry",
            'assert [job.status for job in runtime.flushed] == ["FAILED"]',
            "test_proven_cancel_skips_provider_poll_and_flushes_once",
            'assert pipeline.calls == ["cancel"]',
            'assert pipeline.resume_allow_quality_retry == []',
            'assert [job.status for job in runtime.flushed] == ["CANCELLED"]',
        ),
        "Hosted cancellation runtime regression",
    )
    require_markers(
        pipeline_tests,
        (
            "test_pending_cancel_result_preserves_provider_job_and_waiting_state",
            "test_terminal_non_cancel_result_is_preserved_for_resume_truth",
            "test_cancelled_result_is_only_provider_result_that_marks_job_cancelled",
            "test_missing_provider_recovery_never_self_certifies_cancellation",
            "test_cancellation_terminal_reconciliation_never_launches_quality_retry",
            "test_successful_provider_truth_wins_over_cancellation_intent",
            "test_cancel_transport_error_reconciles_original_provider_success_without_retry",
            "allow_quality_retry=False",
            "assert gateway.poll_count == 1",
            "assert gateway.estimate_count == 0",
            "assert gateway.submit_count == 0",
            "assert costs.calls == 0",
            "assert repository.provider_jobs",
            'assert archived.result.provider_request_id == PROVIDER_REQUEST_ID',
            'assert events.types.count("video_generation.cancelled") == 1',
        ),
        "provider-neutral cancellation executable regression",
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
            "poll the same provider request exactly once",
            "never submits replacement paid provider work",
            "quality retry",
            "WAITING_EXTERNAL",
        ),
        "canonical Video Runtime cancellation semantics",
    )

    require(
        f'- "{SELF_PATH}"' in video_workflow,
        "Video Generation path filter does not react to cancellation contract changes",
    )
    for workflow, label in (
        (video_workflow, "Video Generation workflow"),
        (final_workflow, "Final Acceptance workflow"),
    ):
        require(
            f"python3 {SELF_PATH}" in workflow,
            f"{label} does not directly execute provider-reconciled cancellation contract",
        )
        require(
            workflow.count(SELF_PATH) >= 2,
            f"{label} does not both execute and syntax-gate cancellation contract",
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
