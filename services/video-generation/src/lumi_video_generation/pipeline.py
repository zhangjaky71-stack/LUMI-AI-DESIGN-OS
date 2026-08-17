from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from .gateway_contract import pending_record
from .model import (
    CompiledShot,
    FinalVideoProvenance,
    ShotProvenance,
    ShotRuntime,
    ShotStatus,
    TimelineClip,
    ValidationDecision,
    VideoJob,
    VideoJobStatus,
    VideoTaskSpec,
    VideoTimeline,
)
from .ports import (
    VideoArtifactPort,
    VideoGatewayPort,
    VideoOutputPort,
    VideoRenderPort,
    VideoRepositoryPort,
    VideoValidationPort,
)
from .storyboard import compile_retry, compile_storyboard


class VideoGenerationPipeline:
    """Long-running control plane with bounded provider work per resume."""

    def __init__(
        self,
        *,
        repository: VideoRepositoryPort,
        gateway: VideoGatewayPort,
        output: VideoOutputPort,
        validator: VideoValidationPort,
        renderer: VideoRenderPort,
        artifacts: VideoArtifactPort,
        max_shot_retries: int = 1,
    ) -> None:
        if max_shot_retries < 0:
            raise ValueError("max_shot_retries cannot be negative")
        self.repository = repository
        self.gateway = gateway
        self.output = output
        self.validator = validator
        self.renderer = renderer
        self.artifacts = artifacts
        self.max_shot_retries = max_shot_retries

    async def start(self, spec: VideoTaskSpec) -> VideoJob:
        compiled = compile_storyboard(spec)
        job = VideoJob(
            job_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"lumi:video-job:{spec.organization_id}:{spec.operation_id}",
                )
            ),
            spec=spec,
            status=VideoJobStatus.PLANNED,
            shots=tuple(ShotRuntime(item) for item in compiled),
        )
        persisted = self.repository.create(job)
        if persisted.status is not VideoJobStatus.PLANNED:
            return persisted

        try:
            estimates = [
                await self.gateway.estimate(spec=spec, shot=item)
                for item in compiled
            ]
        except Exception as exc:
            return self.repository.save(
                replace(
                    job,
                    status=VideoJobStatus.FAILED,
                    error_code=f"VIDEO_ESTIMATE_FAILED:{type(exc).__name__}",
                )
            )

        estimate_total = sum(
            (item.amount_usd for item in estimates),
            Decimal("0"),
        )
        if (
            spec.budget_limit_usd is not None
            and estimate_total > spec.budget_limit_usd
        ):
            return self.repository.save(
                replace(
                    job,
                    status=VideoJobStatus.FAILED,
                    error_code="VIDEO_BUDGET_ESTIMATE_EXCEEDED",
                )
            )

        runtimes: list[ShotRuntime] = []
        for item in compiled:
            try:
                result = await self.gateway.submit(spec=spec, shot=item)
            except Exception as exc:
                return await self._abort_partial_submit(
                    job,
                    runtimes,
                    item,
                    f"VIDEO_SUBMIT_FAILED:{type(exc).__name__}",
                )
            if result.status != "PENDING" or not result.provider_request_id:
                return await self._abort_partial_submit(
                    job,
                    runtimes,
                    item,
                    "VIDEO_PROVIDER_ASYNC_SUBMIT_REQUIRED",
                )
            runtimes.append(
                ShotRuntime(
                    compiled=item,
                    status=ShotStatus.WAITING_EXTERNAL,
                    pending=pending_record(item, result),
                )
            )
        return self.repository.save(
            replace(
                job,
                status=VideoJobStatus.WAITING_EXTERNAL,
                shots=tuple(runtimes),
            )
        )

    async def _abort_partial_submit(
        self,
        job: VideoJob,
        submitted: list[ShotRuntime],
        failed_shot: CompiledShot,
        error_code: str,
    ) -> VideoJob:
        cancelled: list[ShotRuntime] = []
        unresolved = False
        for runtime in submitted:
            if runtime.pending is None:
                cancelled.append(runtime)
                continue
            try:
                accepted = await self.gateway.cancel(pending=runtime.pending)
            except Exception:
                accepted = False
            if accepted:
                cancelled.append(
                    replace(
                        runtime,
                        status=ShotStatus.CANCELLED,
                        pending=None,
                    )
                )
            else:
                unresolved = True
                cancelled.append(runtime)
        cancelled.append(
            ShotRuntime(
                compiled=failed_shot,
                status=ShotStatus.FAILED,
                error_code=error_code,
            )
        )
        seen = {item.compiled.shot.shot_id for item in cancelled}
        cancelled.extend(
            ShotRuntime(item)
            for item in compile_storyboard(job.spec)
            if item.shot.shot_id not in seen
        )
        status = (
            VideoJobStatus.CANCEL_REQUESTED
            if unresolved
            else VideoJobStatus.FAILED
        )
        return self.repository.save(
            replace(
                job,
                status=status,
                shots=tuple(cancelled),
                error_code=error_code,
            )
        )

    async def resume(self, job_id: str) -> VideoJob:
        job = self.repository.get(job_id)
        if job.status in {
            VideoJobStatus.COMPLETED,
            VideoJobStatus.CANCELLED,
            VideoJobStatus.FAILED,
        }:
            return job

        updated: list[ShotRuntime] = []
        for runtime in job.shots:
            if (
                runtime.status is not ShotStatus.WAITING_EXTERNAL
                or runtime.pending is None
            ):
                updated.append(runtime)
                continue
            try:
                result = await self.gateway.poll(pending=runtime.pending)
            except Exception as exc:
                updated.append(
                    replace(
                        runtime,
                        error_code=f"VIDEO_POLL_TRANSIENT:{type(exc).__name__}",
                    )
                )
                continue
            if result.status == "PENDING":
                updated.append(replace(runtime, error_code=None))
                continue
            if job.status is VideoJobStatus.CANCEL_REQUESTED:
                updated.append(
                    replace(
                        runtime,
                        status=ShotStatus.CANCELLED,
                        pending=None,
                        error_code=None,
                    )
                )
                continue
            if result.status == "CANCELLED":
                updated.append(
                    replace(
                        runtime,
                        status=ShotStatus.CANCELLED,
                        pending=None,
                        error_code=None,
                    )
                )
                continue
            if result.status != "COMPLETED":
                updated.append(
                    replace(
                        runtime,
                        status=ShotStatus.FAILED,
                        error_code="VIDEO_PROVIDER_FAILED",
                    )
                )
                continue

            try:
                clip = await self.output.materialize_and_validate(
                    spec=job.spec,
                    shot=runtime.compiled,
                    result=result,
                )
            except Exception as exc:
                updated.append(
                    replace(
                        runtime,
                        status=ShotStatus.FAILED,
                        actual_cost_usd=result.cost_usd or Decimal("0"),
                        error_code=f"VIDEO_OUTPUT_INVALID:{type(exc).__name__}",
                    )
                )
                continue

            try:
                report = await self.validator.validate(
                    spec=job.spec,
                    shot=runtime.compiled,
                    clip=clip,
                    provider_result=result,
                )
            except Exception as exc:
                updated.append(
                    replace(
                        runtime,
                        status=ShotStatus.FAILED,
                        clip=clip,
                        actual_cost_usd=result.cost_usd or Decimal("0"),
                        error_code=f"VIDEO_VALIDATION_EXCEPTION:{type(exc).__name__}",
                    )
                )
                continue

            if report.decision is ValidationDecision.REJECT:
                updated.append(
                    replace(
                        runtime,
                        status=ShotStatus.FAILED,
                        clip=clip,
                        validation=report,
                        actual_cost_usd=result.cost_usd or Decimal("0"),
                        error_code="VIDEO_SHOT_VALIDATION_REJECTED",
                    )
                )
                continue

            ready = replace(
                runtime,
                status=ShotStatus.READY,
                pending=None,
                clip=clip,
                validation=report,
                actual_cost_usd=result.cost_usd or Decimal("0"),
                error_code=None,
            )
            try:
                artifact_version_id = await self.artifacts.append_clip(
                    job=job,
                    clip=clip,
                )
            except Exception as exc:
                updated.append(
                    replace(
                        ready,
                        status=ShotStatus.FAILED,
                        error_code=f"VIDEO_CLIP_ARTIFACT_FAILED:{type(exc).__name__}",
                    )
                )
                continue
            updated.append(
                replace(ready, artifact_version_id=artifact_version_id)
            )

        next_job = replace(job, shots=tuple(updated))
        if job.status is VideoJobStatus.CANCEL_REQUESTED:
            if all(
                item.status
                in {
                    ShotStatus.CANCELLED,
                    ShotStatus.READY,
                    ShotStatus.FAILED,
                    ShotStatus.PLANNED,
                }
                for item in updated
            ):
                next_job = replace(
                    next_job,
                    status=VideoJobStatus.CANCELLED,
                )
            return self.repository.save(next_job)
        if any(item.status is ShotStatus.FAILED for item in updated):
            return self.repository.save(
                replace(
                    next_job,
                    status=VideoJobStatus.FAILED,
                    error_code="VIDEO_SHOT_FAILED",
                )
            )
        if any(
            item.status is ShotStatus.WAITING_EXTERNAL
            for item in updated
        ):
            return self.repository.save(
                replace(
                    next_job,
                    status=VideoJobStatus.WAITING_EXTERNAL,
                    error_code=None,
                )
            )
        if not all(item.status is ShotStatus.READY for item in updated):
            return self.repository.save(next_job)
        return await self._compose(
            replace(next_job, status=VideoJobStatus.COMPOSING)
        )

    async def retry_shot(self, job_id: str, shot_id: str) -> VideoJob:
        job = self.repository.get(job_id)
        if job.status not in {
            VideoJobStatus.FAILED,
            VideoJobStatus.WAITING_EXTERNAL,
        }:
            raise ValueError("VIDEO_JOB_NOT_RETRYABLE")
        runtimes = list(job.shots)
        index = next(
            (
                idx
                for idx, item in enumerate(runtimes)
                if item.compiled.shot.shot_id == shot_id
            ),
            None,
        )
        if index is None:
            raise KeyError("VIDEO_SHOT_NOT_FOUND")
        previous = runtimes[index]
        if previous.status is not ShotStatus.FAILED:
            raise ValueError("VIDEO_SHOT_NOT_FAILED")
        if previous.compiled.retry_ordinal >= self.max_shot_retries:
            raise ValueError("VIDEO_SHOT_RETRY_LIMIT_EXCEEDED")
        retry = compile_retry(job.spec, previous.compiled)
        failed_provider: str | None = None
        if previous.clip is not None:
            failed_provider = previous.clip.provider
        elif previous.pending is not None:
            failed_provider = previous.pending.result.provider
        excluded = (failed_provider,) if failed_provider else ()
        result = await self.gateway.submit(
            spec=job.spec,
            shot=retry,
            excluded_provider_keys=excluded,
        )
        if result.status != "PENDING" or not result.provider_request_id:
            raise ValueError("VIDEO_PROVIDER_ASYNC_SUBMIT_REQUIRED")
        runtimes[index] = ShotRuntime(
            compiled=retry,
            status=ShotStatus.WAITING_EXTERNAL,
            pending=pending_record(retry, result),
        )
        return self.repository.save(
            replace(
                job,
                status=VideoJobStatus.WAITING_EXTERNAL,
                shots=tuple(runtimes),
                error_code=None,
            )
        )

    async def cancel(self, job_id: str) -> VideoJob:
        job = self.repository.get(job_id)
        if job.status in {
            VideoJobStatus.COMPLETED,
            VideoJobStatus.CANCELLED,
        }:
            return job
        runtimes: list[ShotRuntime] = []
        any_pending = False
        for runtime in job.shots:
            if (
                runtime.status is not ShotStatus.WAITING_EXTERNAL
                or runtime.pending is None
            ):
                runtimes.append(runtime)
                continue
            try:
                accepted = await self.gateway.cancel(pending=runtime.pending)
            except Exception:
                accepted = False
            if accepted:
                runtimes.append(
                    replace(
                        runtime,
                        status=ShotStatus.CANCELLED,
                        pending=None,
                        error_code=None,
                    )
                )
            else:
                any_pending = True
                runtimes.append(runtime)
        status = (
            VideoJobStatus.CANCEL_REQUESTED
            if any_pending
            else VideoJobStatus.CANCELLED
        )
        return self.repository.save(
            replace(job, status=status, shots=tuple(runtimes))
        )

    async def _compose(self, job: VideoJob) -> VideoJob:
        start = Decimal("0")
        clips: list[TimelineClip] = []
        provenance: list[ShotProvenance] = []
        for runtime in job.shots:
            if runtime.clip is None:
                raise ValueError("VIDEO_READY_SHOT_CLIP_REQUIRED")
            if runtime.artifact_version_id is None:
                raise ValueError("VIDEO_READY_SHOT_ARTIFACT_REQUIRED")
            shot = runtime.compiled.shot
            clips.append(
                TimelineClip(
                    shot_id=shot.shot_id,
                    durable_ref=runtime.clip.durable_ref,
                    start_seconds=start,
                    duration_seconds=shot.duration_seconds,
                    transition=shot.transition,
                )
            )
            start += shot.duration_seconds
            rights: tuple[str, ...] = ()
            assets: tuple[str, ...] = ()
            if shot.source_ref is not None:
                rights = (shot.source_ref.rights_snapshot_id,)
                assets = (shot.source_ref.asset_id,)
            provenance.append(
                ShotProvenance(
                    shot_id=shot.shot_id,
                    operation_id=runtime.compiled.paid_operation_id,
                    retry_ordinal=runtime.compiled.retry_ordinal,
                    provider=runtime.clip.provider,
                    model=runtime.clip.model,
                    provider_request_id=runtime.clip.provider_request_id,
                    source_asset_ids=assets,
                    identity_refs=shot.identity_refs,
                    rights_snapshot_ids=rights,
                    cost_usd=runtime.actual_cost_usd,
                    artifact_version_id=runtime.artifact_version_id,
                )
            )
        timeline = VideoTimeline(
            clips=tuple(clips),
            width=job.spec.width,
            height=job.spec.height,
            fps=job.spec.fps,
        )
        try:
            rendered = await self.renderer.render(timeline=timeline)
        except Exception as exc:
            return self.repository.save(
                replace(
                    job,
                    status=VideoJobStatus.FAILED,
                    error_code=f"VIDEO_COMPOSITION_FAILED:{type(exc).__name__}",
                )
            )
        final_provenance = FinalVideoProvenance(
            task_semantic_hash=job.spec.semantic_hash(),
            source_shots=tuple(provenance),
            renderer_version=rendered.renderer_version,
            brand_rule_snapshot_id=job.spec.brand_rule_snapshot_id,
            agent_run_id=job.spec.agent_run_id,
            agent_id=job.spec.agent_id,
            recipe_id=job.spec.recipe_id,
            skill_refs=job.spec.skill_refs,
            git_commit=job.spec.git_commit,
        )
        provisional = replace(
            job,
            final_video=rendered,
            provenance=final_provenance,
            error_code=None,
        )
        try:
            final_artifact_version_id = await self.artifacts.append_final(
                job=provisional,
                video=rendered,
            )
        except Exception as exc:
            return self.repository.save(
                replace(
                    provisional,
                    status=VideoJobStatus.FAILED,
                    error_code=f"VIDEO_FINAL_ARTIFACT_FAILED:{type(exc).__name__}",
                )
            )
        return self.repository.save(
            replace(
                provisional,
                status=VideoJobStatus.COMPLETED,
                final_artifact_version_id=final_artifact_version_id,
            )
        )
