from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from lumi_video_generation.model import ShotRuntime, VideoJob, VideoTaskSpec
from lumi_worker_media.job_runtime import ExternalWait
from lumi_worker_media.queue_contracts import JobMessage
from lumi_worker_media.video_generation_runtime import HostedVideoGenerationRuntime

ORG = UUID("01900000-0000-7000-8000-000000000001")
PROJECT = UUID("01900000-0000-7000-8000-000000000006")
TASK = UUID("01900000-0000-7000-8000-000000000101")
OPERATION = UUID("01900000-0000-7000-8000-000000000102")


def _spec() -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=str(ORG),
        project_id=str(PROJECT),
        task_id=str(TASK),
        operation_id=str(OPERATION),
        mode="TEXT_TO_VIDEO",
        prompt="Cancellation reconciliation contract",
        duration_seconds=Decimal("4"),
        aspect_ratio="16:9",
        width=1280,
        height=720,
        fps=24,
        budget_limit_usd=Decimal("5"),
        code_git_sha="c" * 40,
    )


def _message() -> JobMessage:
    return JobMessage(
        job_id=TASK,
        organization_id=ORG,
        project_id=PROJECT,
        operation_id=OPERATION,
        trace_id="trace-video-cancel-runtime",
    )


def _job(status: str, *, waiting: bool = False) -> VideoJob:
    shots = ()
    if waiting:
        shots = (
            ShotRuntime(
                shot_id="shot-1",
                ordinal=1,
                paid_operation_id="01900000-0000-7000-8000-000000000103",
                status="WAITING_EXTERNAL",
                attempt_count=1,
                provider="openai",
                model="sora-2",
                provider_request_id="video_provider_request_1",
            ),
        )
    return VideoJob(
        video_job_id="video-job-cancel-runtime",
        organization_id=str(ORG),
        operation_id=str(OPERATION),
        semantic_hash="a" * 64,
        storyboard_hash="b" * 64,
        status=status,  # type: ignore[arg-type]
        shots=shots,
        estimated_cost_usd=Decimal("1.25"),
        actual_cost_usd=Decimal("1.25"),
    )


class _Repository:
    def __init__(self, dsn: str) -> None:
        assert dsn.startswith("postgresql://")

    async def load(self, *, organization_id: str, operation_id: str):
        assert organization_id == str(ORG)
        assert operation_id == str(OPERATION)
        return SimpleNamespace(video_job_id="video-job-cancel-runtime")


class _Pipeline:
    def __init__(self, *, cancel_job: VideoJob, resume_job: VideoJob | None) -> None:
        self.cancel_job = cancel_job
        self.resume_job = resume_job
        self.calls: list[str] = []
        self.resume_allow_quality_retry: list[bool] = []

    async def cancel(self, *, organization_id: str, video_job_id: str) -> VideoJob:
        assert organization_id == str(ORG)
        assert video_job_id == "video-job-cancel-runtime"
        self.calls.append("cancel")
        return self.cancel_job

    async def resume(
        self,
        *,
        organization_id: str,
        video_job_id: str,
        allow_quality_retry: bool = True,
    ) -> VideoJob:
        assert organization_id == str(ORG)
        assert video_job_id == "video-job-cancel-runtime"
        self.calls.append("resume")
        self.resume_allow_quality_retry.append(allow_quality_retry)
        if self.resume_job is None:
            raise AssertionError("resume must not be called")
        return self.resume_job


class _Runtime(HostedVideoGenerationRuntime):
    def __init__(self, *, spec: VideoTaskSpec, pipeline: _Pipeline) -> None:
        super().__init__(
            database_dsn="postgresql://runtime:runtime@db/lumi",
            asset_bucket="lumi-assets",
            poll_seconds=15,
        )
        self.spec = spec
        self.pipeline = pipeline
        self.flushed: list[VideoJob] = []

    async def _load_spec(self, message: JobMessage) -> VideoTaskSpec:
        assert message == _message()
        return self.spec

    def _build_pipeline(self, spec: VideoTaskSpec, repository):
        assert spec == self.spec
        assert isinstance(repository, _Repository)
        return self.pipeline, object(), object()

    async def _flush_job(
        self,
        *,
        spec: VideoTaskSpec,
        job: VideoJob,
        repository,
        events,
        output_recovery,
    ) -> None:
        assert spec == self.spec
        assert isinstance(repository, _Repository)
        self.flushed.append(job)


def test_unproven_cancel_polls_same_provider_once_before_single_flush(monkeypatch) -> None:
    from lumi_worker_media import video_generation_runtime as module

    pipeline = _Pipeline(
        cancel_job=_job("WAITING_EXTERNAL", waiting=True),
        resume_job=_job("COMPLETED"),
    )
    runtime = _Runtime(spec=_spec(), pipeline=pipeline)
    monkeypatch.setattr(module, "PostgresVideoRepository", _Repository)

    result = asyncio.run(runtime.reconcile_cancellation(_message()))

    assert not isinstance(result, ExternalWait)
    assert result["status"] == "COMPLETED"
    assert pipeline.calls == ["cancel", "resume"]
    assert pipeline.resume_allow_quality_retry == [False]
    assert [job.status for job in runtime.flushed] == ["COMPLETED"]


def test_still_pending_after_cancel_poll_remains_external_wait(monkeypatch) -> None:
    from lumi_worker_media import video_generation_runtime as module

    pipeline = _Pipeline(
        cancel_job=_job("WAITING_EXTERNAL", waiting=True),
        resume_job=_job("WAITING_EXTERNAL", waiting=True),
    )
    runtime = _Runtime(spec=_spec(), pipeline=pipeline)
    monkeypatch.setattr(module, "PostgresVideoRepository", _Repository)

    result = asyncio.run(runtime.reconcile_cancellation(_message()))

    assert isinstance(result, ExternalWait)
    assert result.wait_reason == "video_provider_pending"
    assert pipeline.calls == ["cancel", "resume"]
    assert pipeline.resume_allow_quality_retry == [False]
    assert [job.status for job in runtime.flushed] == ["WAITING_EXTERNAL"]


def test_failed_provider_truth_does_not_enable_quality_retry(monkeypatch) -> None:
    from lumi_worker_media import video_generation_runtime as module

    pipeline = _Pipeline(
        cancel_job=_job("WAITING_EXTERNAL", waiting=True),
        resume_job=_job("FAILED"),
    )
    runtime = _Runtime(spec=_spec(), pipeline=pipeline)
    monkeypatch.setattr(module, "PostgresVideoRepository", _Repository)

    result = asyncio.run(runtime.reconcile_cancellation(_message()))

    assert not isinstance(result, ExternalWait)
    assert result["status"] == "FAILED"
    assert pipeline.calls == ["cancel", "resume"]
    assert pipeline.resume_allow_quality_retry == [False]
    assert [job.status for job in runtime.flushed] == ["FAILED"]


def test_proven_cancel_skips_provider_poll_and_flushes_once(monkeypatch) -> None:
    from lumi_worker_media import video_generation_runtime as module

    pipeline = _Pipeline(
        cancel_job=_job("CANCELLED"),
        resume_job=None,
    )
    runtime = _Runtime(spec=_spec(), pipeline=pipeline)
    monkeypatch.setattr(module, "PostgresVideoRepository", _Repository)

    result = asyncio.run(runtime.reconcile_cancellation(_message()))

    assert not isinstance(result, ExternalWait)
    assert result["status"] == "CANCELLED"
    assert pipeline.calls == ["cancel"]
    assert pipeline.resume_allow_quality_retry == []
    assert [job.status for job in runtime.flushed] == ["CANCELLED"]
