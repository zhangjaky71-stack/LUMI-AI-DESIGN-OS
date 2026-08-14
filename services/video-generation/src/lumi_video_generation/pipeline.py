from __future__ import annotations

import hashlib
from dataclasses import replace

from .model import (
    CompiledShot,
    FinalVideoProvenance,
    GatewayVideoResult,
    ProviderJobRecord,
    ShotProvenance,
    ShotRuntime,
    TimelineAudioTrack,
    TimelineClip,
    TimelineTransition,
    VideoJob,
    VideoOutputSpec,
    VideoTaskSpec,
    VideoTimeline,
    timeline_hash,
)
from .ports import MediaSandboxPort, VideoArtifactPort, VideoCostPort, VideoEventPort, VideoGatewayPort, VideoOutputPort, VideoRepositoryPort, VideoValidationPort
from .repository import VideoOperationConflict
from .storyboard import compile_storyboard


def _job_id(spec: VideoTaskSpec) -> str:
    digest = hashlib.sha256(f"{spec.organization_id}:{spec.operation_id}:{spec.semantic_hash}".encode()).hexdigest()
    return f"video-job:{digest}"


def _replace_shot(job: VideoJob, updated: ShotRuntime) -> VideoJob:
    return replace(job, shots=tuple(updated if item.shot_id == updated.shot_id else item for item in job.shots))


def _request_hash(spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> str:
    return hashlib.sha256(f"{spec.semantic_hash}:{shot.paid_operation_id}:{':'.join(continuity_refs)}".encode()).hexdigest()


def _prompt_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class VideoGenerationPipeline:
    """Long-running state machine. A provider poll is performed at most once per resume call."""

    def __init__(
        self,
        *,
        repository: VideoRepositoryPort,
        gateway: VideoGatewayPort,
        output: VideoOutputPort,
        validator: VideoValidationPort,
        artifacts: VideoArtifactPort,
        sandbox: MediaSandboxPort,
        costs: VideoCostPort,
        events: VideoEventPort,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.output = output
        self.validator = validator
        self.artifacts = artifacts
        self.sandbox = sandbox
        self.costs = costs
        self.events = events

    async def start(self, spec: VideoTaskSpec) -> VideoJob:
        existing = self.repository.get_by_operation(spec.organization_id, spec.operation_id)
        if existing is not None:
            if existing.semantic_hash != spec.semantic_hash:
                raise VideoOperationConflict("VIDEO_OPERATION_SEMANTIC_CONFLICT")
            return existing
        storyboard = compile_storyboard(spec)
        job = VideoJob(
            video_job_id=_job_id(spec),
            organization_id=spec.organization_id,
            operation_id=spec.operation_id,
            semantic_hash=spec.semantic_hash,
            storyboard_hash=storyboard.storyboard_hash,
            status="SUBMITTING",
            shots=tuple(ShotRuntime(shot_id=item.shot.shot_id, ordinal=item.ordinal, paid_operation_id=item.paid_operation_id) for item in storyboard.shots),
        )
        self.repository.save_spec(spec)
        self.repository.save(job)
        await self.events.emit(
            "video_generation.started",
            organization_id=spec.organization_id,
            video_job_id=job.video_job_id,
            payload={"shot_count": len(job.shots), "storyboard_hash": storyboard.storyboard_hash},
        )
        return await self._advance(spec, job)

    async def resume(self, *, organization_id: str, video_job_id: str) -> VideoJob:
        job = self.repository.get(organization_id, video_job_id)
        if job is None:
            raise ValueError("VIDEO_JOB_NOT_FOUND")
        if job.status in {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
            return job
        spec = self.repository.get_spec(organization_id, job.operation_id)
        if spec is None:
            raise ValueError("VIDEO_SPEC_SNAPSHOT_MISSING")
        waiting = next((item for item in job.shots if item.status == "WAITING_EXTERNAL"), None)
        if waiting is None:
            return await self._advance(spec, job)
        pending = self.repository.get_provider_job(organization_id, video_job_id, waiting.shot_id)
        if pending is None:
            return self._fail_job(job, waiting, "VIDEO_PROVIDER_JOB_STATE_MISSING")
        try:
            result = await self.gateway.poll(pending=pending)
        except Exception:
            return job
        if result.status == "PENDING":
            self.repository.save_provider_job(replace(pending, result=result))
            return job
        self.repository.delete_provider_job(organization_id, video_job_id, waiting.shot_id)
        compiled = next(item for item in compile_storyboard(spec).shots if item.shot.shot_id == waiting.shot_id)
        job = await self._finish_terminal(spec, job, compiled, result)
        return await self._advance(spec, job)

    async def cancel(self, *, organization_id: str, video_job_id: str) -> VideoJob:
        job = self.repository.get(organization_id, video_job_id)
        if job is None:
            raise ValueError("VIDEO_JOB_NOT_FOUND")
        if job.status in {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
            return job
        waiting = next((item for item in job.shots if item.status == "WAITING_EXTERNAL"), None)
        if waiting is not None:
            pending = self.repository.get_provider_job(organization_id, video_job_id, waiting.shot_id)
            if pending is not None:
                try:
                    result = await self.gateway.cancel(pending=pending)
                except Exception:
                    return job
                job = await self._record_cost(job, waiting, result)
                self.repository.delete_provider_job(organization_id, video_job_id, waiting.shot_id)
        cancelled = replace(
            job,
            shots=tuple(replace(item, status="CANCELLED") if item.status in {"QUEUED", "WAITING_EXTERNAL"} else item for item in job.shots),
            status="CANCELLED",
            error_code="VIDEO_CANCELLED_BY_REQUEST",
        )
        self.repository.save(cancelled)
        await self.events.emit("video_generation.cancelled", organization_id=organization_id, video_job_id=video_job_id, payload={"status": "CANCELLED"})
        return cancelled

    async def _advance(self, spec: VideoTaskSpec, job: VideoJob) -> VideoJob:
        if job.status in {"FAILED", "CANCELLED", "COMPLETED", "PARTIAL"}:
            return job
        storyboard = compile_storyboard(spec)
        while True:
            if any(item.status == "WAITING_EXTERNAL" for item in job.shots):
                waiting = replace(job, status="WAITING_EXTERNAL")
                self.repository.save(waiting)
                return waiting
            required_failure = next(
                (
                    runtime
                    for runtime in job.shots
                    if runtime.status == "FAILED"
                    and not next(item.shot.optional for item in storyboard.shots if item.shot.shot_id == runtime.shot_id)
                ),
                None,
            )
            if required_failure is not None:
                failed = replace(job, status="FAILED", error_code=required_failure.error_code or "VIDEO_REQUIRED_SHOT_FAILED")
                self.repository.save(failed)
                return failed
            queued = next((item for item in job.shots if item.status == "QUEUED"), None)
            if queued is None:
                return await self._compose(spec, job)
            compiled = next(item for item in storyboard.shots if item.shot.shot_id == queued.shot_id)
            continuity_refs, _ = self._continuity(job, storyboard.shots, compiled)
            if compiled.shot.source_ref is not None and not compiled.shot.source_ref.commercial_use_allowed:
                return self._fail_job(job, queued, "VIDEO_SOURCE_COMMERCIAL_RIGHTS_NOT_ALLOWED")
            try:
                estimate = await self.gateway.estimate(spec=spec, shot=compiled, continuity_refs=continuity_refs)
            except Exception as exc:
                return self._fail_job(job, queued, f"VIDEO_ESTIMATE_EXCEPTION:{type(exc).__name__}")
            next_estimated = job.estimated_cost_usd + estimate.amount_usd
            if next_estimated > spec.budget_limit_usd:
                if compiled.shot.optional and spec.allow_optional_shot_drop:
                    dropped = replace(queued, status="DROPPED", error_code="VIDEO_OPTIONAL_SHOT_DROPPED_FOR_BUDGET")
                    job = _replace_shot(job, dropped)
                    self.repository.save(job)
                    continue
                return self._fail_job(job, queued, "VIDEO_TASK_BUDGET_EXCEEDED")
            job = replace(job, estimated_cost_usd=next_estimated, status="SUBMITTING")
            self.repository.save(job)
            try:
                result = await self.gateway.submit(spec=spec, shot=compiled, continuity_refs=continuity_refs)
            except Exception as exc:
                return self._fail_job(job, queued, f"VIDEO_GATEWAY_SUBMIT_EXCEPTION:{type(exc).__name__}")
            if result.status == "PENDING":
                if not result.provider_request_id:
                    return self._fail_job(job, queued, "VIDEO_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
                self.repository.save_provider_job(ProviderJobRecord(
                    organization_id=spec.organization_id,
                    video_job_id=job.video_job_id,
                    shot_id=queued.shot_id,
                    paid_operation_id=compiled.paid_operation_id,
                    request_hash=_request_hash(spec, compiled, continuity_refs),
                    result=result,
                ))
                waiting_shot = replace(queued, status="WAITING_EXTERNAL", provider=result.provider, model=result.model, provider_request_id=result.provider_request_id)
                job = _replace_shot(job, waiting_shot)
                waiting_job = replace(job, status="WAITING_EXTERNAL")
                self.repository.save(waiting_job)
                await self.events.emit(
                    "video_generation.external_wait",
                    organization_id=spec.organization_id,
                    video_job_id=job.video_job_id,
                    payload={"shot_id": queued.shot_id, "provider_request_id": result.provider_request_id},
                )
                return waiting_job
            job = await self._finish_terminal(spec, job, compiled, result)
            if job.status == "FAILED":
                return job

    async def _finish_terminal(self, spec: VideoTaskSpec, job: VideoJob, shot: CompiledShot, result: GatewayVideoResult) -> VideoJob:
        runtime = next(item for item in job.shots if item.shot_id == shot.shot.shot_id)
        job = await self._record_cost(job, runtime, result)
        if result.status != "SUCCEEDED" or not result.output_ref:
            if shot.shot.optional and spec.allow_optional_shot_drop:
                dropped = replace(runtime, status="DROPPED", provider=result.provider, model=result.model, provider_request_id=result.provider_request_id, error_code=f"VIDEO_OPTIONAL_SHOT_{result.status}")
                job = _replace_shot(job, dropped)
                self.repository.save(job)
                return job
            return self._fail_job(job, runtime, f"VIDEO_PROVIDER_{result.status}")
        try:
            clip, probe = await self.output.materialize_and_probe(spec=spec, shot=shot, output_ref=result.output_ref, declared_mime_type=result.output_mime_type)
            validation = await self.validator.validate_shot(spec=spec, shot=shot, clip=clip, probe=probe, safety_metadata=result.safety_metadata)
        except Exception as exc:
            if shot.shot.optional and spec.allow_optional_shot_drop:
                dropped = replace(runtime, status="DROPPED", error_code=f"VIDEO_OPTIONAL_POSTPROCESS:{type(exc).__name__}")
                job = _replace_shot(job, dropped)
                self.repository.save(job)
                return job
            return self._fail_job(job, runtime, f"VIDEO_POSTPROCESS_EXCEPTION:{type(exc).__name__}")
        continuity_refs, continuity_parent_ids = self._continuity(job, compile_storyboard(spec).shots, shot)
        provenance = ShotProvenance(
            video_job_id=job.video_job_id,
            organization_id=spec.organization_id,
            shot_id=shot.shot.shot_id,
            paid_operation_id=shot.paid_operation_id,
            storyboard_hash=job.storyboard_hash,
            prompt_hash=_prompt_hash(shot.shot.prompt),
            source_refs=(shot.shot.source_ref.durable_ref,) if shot.shot.source_ref else (),
            continuity_refs=continuity_refs,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            routing_reason_codes=result.routing_reason_codes,
            pricing_snapshot_id=result.pricing_snapshot_id,
            cost_usd=result.cost_usd,
            cost_confidence=result.cost_confidence,
            brand_rule_set_version=spec.brand_rule_set_version,
            identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
            code_git_sha=spec.code_git_sha,
        )
        artifact_version_id = await self.artifacts.create_clip(
            spec=spec,
            shot=shot,
            clip=clip,
            provenance=provenance,
            validation=validation,
            continuity_parent_version_ids=continuity_parent_ids,
        )
        if validation.decision == "PASS":
            ready = replace(runtime, status="READY", provider=result.provider, model=result.model, provider_request_id=result.provider_request_id, clip_artifact_version_id=artifact_version_id, clip=clip, validation=validation)
            job = _replace_shot(job, ready)
            self.repository.save(job)
            await self.events.emit("video_generation.shot_ready", organization_id=spec.organization_id, video_job_id=job.video_job_id, payload={"shot_id": shot.shot.shot_id, "artifact_version_id": artifact_version_id})
            return job
        if shot.shot.optional and spec.allow_optional_shot_drop:
            dropped = replace(runtime, status="DROPPED", clip_artifact_version_id=artifact_version_id, clip=clip, validation=validation, error_code="VIDEO_OPTIONAL_SHOT_VALIDATION_FAILED")
            job = _replace_shot(job, dropped)
            self.repository.save(job)
            return job
        failed = replace(runtime, status="FAILED", clip_artifact_version_id=artifact_version_id, clip=clip, validation=validation, error_code="VIDEO_SHOT_VALIDATION_FAILED")
        failed_job = replace(_replace_shot(job, failed), status="FAILED", error_code="VIDEO_SHOT_VALIDATION_FAILED")
        self.repository.save(failed_job)
        return failed_job

    async def _record_cost(self, job: VideoJob, runtime: ShotRuntime, result: GatewayVideoResult) -> VideoJob:
        inserted = await self.costs.record_terminal(
            video_job_id=job.video_job_id,
            shot_id=runtime.shot_id,
            paid_operation_id=runtime.paid_operation_id,
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id,
            amount_usd=result.cost_usd,
            confidence=result.cost_confidence,
            pricing_snapshot_id=result.pricing_snapshot_id,
        )
        if not inserted or result.cost_usd is None:
            return job
        updated = replace(job, actual_cost_usd=job.actual_cost_usd + result.cost_usd)
        self.repository.save(updated)
        return updated

    def _continuity(self, job: VideoJob, storyboard: tuple[CompiledShot, ...], shot: CompiledShot) -> tuple[tuple[str, ...], tuple[str, ...]]:
        refs: list[str] = []
        parent_ids: list[str] = []
        for continuity in shot.shot.continuity_refs:
            if continuity.durable_ref:
                refs.append(continuity.durable_ref)
            if continuity.source_shot_id:
                source = next((item for item in job.shots if item.shot_id == continuity.source_shot_id), None)
                if source is None or source.status != "READY" or source.clip is None or not source.clip.tail_frame_ref:
                    raise ValueError("VIDEO_CONTINUITY_DEPENDENCY_NOT_READY")
                refs.append(source.clip.tail_frame_ref)
                if source.clip_artifact_version_id:
                    parent_ids.append(source.clip_artifact_version_id)
        if shot.ordinal > 1 and not any(item.kind == "PREVIOUS_TAIL" for item in shot.shot.continuity_refs):
            previous_id = storyboard[shot.ordinal - 2].shot.shot_id
            previous = next(item for item in job.shots if item.shot_id == previous_id)
            if previous.status == "READY" and previous.clip is not None and previous.clip.tail_frame_ref:
                refs.append(previous.clip.tail_frame_ref)
                if previous.clip_artifact_version_id:
                    parent_ids.append(previous.clip_artifact_version_id)
        return tuple(dict.fromkeys(refs)), tuple(dict.fromkeys(parent_ids))

    async def _compose(self, spec: VideoTaskSpec, job: VideoJob) -> VideoJob:
        ready = [item for item in sorted(job.shots, key=lambda value: value.ordinal) if item.status == "READY" and item.clip is not None and item.clip_artifact_version_id]
        if not ready:
            failed = replace(job, status="FAILED", error_code="VIDEO_NO_READY_SHOTS")
            self.repository.save(failed)
            return failed
        storyboard = compile_storyboard(spec)
        clips = tuple(
            TimelineClip(
                shot_id=item.shot_id,
                artifact_version_id=item.clip_artifact_version_id or "",
                durable_ref=item.clip.durable_asset_ref if item.clip else "",
                duration_seconds=next(compiled.shot.duration_seconds for compiled in storyboard.shots if compiled.shot.shot_id == item.shot_id),
            )
            for item in ready
        )
        transitions = tuple(
            TimelineTransition(
                from_shot_id=clips[index].shot_id,
                to_shot_id=clips[index + 1].shot_id,
                kind=next(compiled.shot.transition_to_next for compiled in storyboard.shots if compiled.shot.shot_id == clips[index].shot_id),
            )
            for index in range(len(clips) - 1)
        )
        timeline = VideoTimeline(
            clips=clips,
            overlays=(),
            audio_tracks=tuple(TimelineAudioTrack(item.durable_ref, item.offset_seconds, item.gain_db) for item in spec.audio_tracks),
            transitions=transitions,
            output_spec=VideoOutputSpec(width=spec.width, height=spec.height, fps=spec.fps),
        )
        composing = replace(job, status="COMPOSING")
        self.repository.save(composing)
        try:
            rendered = await self.sandbox.render(timeline)
            validation = await self.validator.validate_final(spec=spec, timeline=timeline, rendered=rendered)
        except Exception as exc:
            failed = replace(composing, status="FAILED", error_code=f"VIDEO_COMPOSITION_EXCEPTION:{type(exc).__name__}")
            self.repository.save(failed)
            return failed
        provenance = FinalVideoProvenance(
            video_job_id=job.video_job_id,
            organization_id=spec.organization_id,
            storyboard_hash=job.storyboard_hash,
            clip_artifact_version_ids=tuple(item.artifact_version_id for item in clips),
            timeline_hash=timeline_hash(timeline),
            code_git_sha=spec.code_git_sha,
            brand_rule_set_version=spec.brand_rule_set_version,
        )
        final_version_id = await self.artifacts.create_final(
            spec=spec,
            rendered=rendered,
            provenance=provenance,
            validation=validation,
            clip_artifact_version_ids=provenance.clip_artifact_version_ids,
        )
        if validation.decision != "PASS":
            failed = replace(composing, status="FAILED", final_artifact_version_id=final_version_id, error_code="VIDEO_FINAL_VALIDATION_FAILED")
            self.repository.save(failed)
            return failed
        dropped = any(item.status == "DROPPED" for item in job.shots)
        completed = replace(composing, status="PARTIAL" if dropped else "COMPLETED", final_artifact_version_id=final_version_id, error_code="VIDEO_COMPLETED_WITH_OPTIONAL_DROPS" if dropped else None)
        self.repository.save(completed)
        await self.events.emit("video_generation.completed", organization_id=spec.organization_id, video_job_id=job.video_job_id, payload={"status": completed.status, "artifact_version_id": final_version_id})
        return completed

    def _fail_job(self, job: VideoJob, runtime: ShotRuntime, error_code: str) -> VideoJob:
        failed_shot = replace(runtime, status="FAILED", error_code=error_code)
        failed = replace(_replace_shot(job, failed_shot), status="FAILED", error_code=error_code)
        self.repository.save(failed)
        return failed
