from __future__ import annotations

from decimal import Decimal
from typing import Any

from lumi_video_generation import (
    CompiledShot,
    DurableVideoObject,
    FinalVideoProvenance,
    GatewayVideoResult,
    ProviderJobRecord,
    RenderedVideo,
    ShotRuntime,
    ShotSpec,
    ShotStatus,
    ShotValidationReport,
    SourceImageRef,
    StoredVideoClip,
    ValidationDecision,
    VideoJob,
    VideoJobStatus,
    VideoMode,
    VideoProbeResult,
    VideoTaskSpec,
)
from lumi_video_generation.model import ShotProvenance


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _source(value: dict[str, Any] | None) -> SourceImageRef | None:
    if value is None:
        return None
    return SourceImageRef(
        asset_id=str(value["asset_id"]),
        asset_version=str(value["asset_version"]),
        durable_ref=str(value["durable_ref"]),
        checksum_sha256=str(value["checksum_sha256"]),
        rights_snapshot_id=str(value["rights_snapshot_id"]),
    )


def encode_spec(spec: VideoTaskSpec) -> dict[str, Any]:
    return {
        "organization_id": spec.organization_id,
        "project_id": spec.project_id,
        "task_id": spec.task_id,
        "operation_id": spec.operation_id,
        "mode": spec.mode.value,
        "width": spec.width,
        "height": spec.height,
        "fps": spec.fps,
        "shots": [
            {
                "shot_id": shot.shot_id,
                "duration_seconds": str(shot.duration_seconds),
                "prompt": shot.prompt,
                "source_ref": (
                    None
                    if shot.source_ref is None
                    else {
                        "asset_id": shot.source_ref.asset_id,
                        "asset_version": shot.source_ref.asset_version,
                        "durable_ref": shot.source_ref.durable_ref,
                        "checksum_sha256": shot.source_ref.checksum_sha256,
                        "rights_snapshot_id": shot.source_ref.rights_snapshot_id,
                    }
                ),
                "camera_motion": shot.camera_motion,
                "subject_action": shot.subject_action,
                "transition": shot.transition,
                "identity_refs": list(shot.identity_refs),
                "required_features": sorted(shot.required_features),
            }
            for shot in spec.shots
        ],
        "budget_limit_usd": (
            str(spec.budget_limit_usd)
            if spec.budget_limit_usd is not None
            else None
        ),
        "negative_prompt": spec.negative_prompt,
        "seed": spec.seed,
        "agent_run_id": spec.agent_run_id,
        "brand_rule_snapshot_id": spec.brand_rule_snapshot_id,
        "agent_id": spec.agent_id,
        "recipe_id": spec.recipe_id,
        "skill_refs": list(spec.skill_refs),
        "git_commit": spec.git_commit,
        "user_use_declaration": spec.user_use_declaration,
    }


def decode_spec(value: dict[str, Any]) -> VideoTaskSpec:
    shots = tuple(
        ShotSpec(
            shot_id=str(item["shot_id"]),
            duration_seconds=_decimal(item["duration_seconds"]),
            prompt=str(item["prompt"]),
            source_ref=_source(item.get("source_ref")),
            camera_motion=item.get("camera_motion"),
            subject_action=item.get("subject_action"),
            transition=str(item.get("transition", "CUT")),
            identity_refs=tuple(str(x) for x in item.get("identity_refs", [])),
            required_features=frozenset(
                str(x) for x in item.get("required_features", [])
            ),
        )
        for item in value["shots"]
    )
    budget = value.get("budget_limit_usd")
    return VideoTaskSpec(
        organization_id=str(value["organization_id"]),
        project_id=str(value["project_id"]),
        task_id=str(value["task_id"]),
        operation_id=str(value["operation_id"]),
        mode=VideoMode(str(value["mode"])),
        width=int(value["width"]),
        height=int(value["height"]),
        fps=int(value["fps"]),
        shots=shots,
        budget_limit_usd=None if budget is None else _decimal(budget),
        negative_prompt=value.get("negative_prompt"),
        seed=value.get("seed"),
        agent_run_id=value.get("agent_run_id"),
        brand_rule_snapshot_id=value.get("brand_rule_snapshot_id"),
        agent_id=value.get("agent_id"),
        recipe_id=value.get("recipe_id"),
        skill_refs=tuple(str(x) for x in value.get("skill_refs", [])),
        git_commit=value.get("git_commit"),
        user_use_declaration=value.get("user_use_declaration"),
    )


def _probe(value: dict[str, Any]) -> VideoProbeResult:
    return VideoProbeResult(
        mime_type=str(value["mime_type"]),
        width=int(value["width"]),
        height=int(value["height"]),
        duration_seconds=_decimal(value["duration_seconds"]),
        decodable_frames=int(value["decodable_frames"]),
        black_frame_ratio=_decimal(value.get("black_frame_ratio", "0")),
        has_audio=bool(value.get("has_audio", False)),
    )


def _object(value: dict[str, Any]) -> DurableVideoObject:
    return DurableVideoObject(
        durable_ref=str(value["durable_ref"]),
        bucket=str(value["bucket"]),
        storage_key=str(value["storage_key"]),
        size_bytes=int(value["size_bytes"]),
    )


def _encode_probe(probe: VideoProbeResult) -> dict[str, Any]:
    return {
        "mime_type": probe.mime_type,
        "width": probe.width,
        "height": probe.height,
        "duration_seconds": str(probe.duration_seconds),
        "decodable_frames": probe.decodable_frames,
        "black_frame_ratio": str(probe.black_frame_ratio),
        "has_audio": probe.has_audio,
    }


def _encode_object(value: DurableVideoObject) -> dict[str, Any]:
    return {
        "durable_ref": value.durable_ref,
        "bucket": value.bucket,
        "storage_key": value.storage_key,
        "size_bytes": value.size_bytes,
    }


def _encode_result(result: GatewayVideoResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "provider": result.provider,
        "model": result.model,
        "provider_request_id": result.provider_request_id,
        "output_ref": result.output_ref,
        "output_mime_type": result.output_mime_type,
        "cost_usd": None if result.cost_usd is None else str(result.cost_usd),
        "pricing_snapshot_id": result.pricing_snapshot_id,
        "routing_reason_codes": list(result.routing_reason_codes),
        "safety_metadata": result.safety_metadata,
        "finish_reason": result.finish_reason,
    }


def _decode_result(value: dict[str, Any]) -> GatewayVideoResult:
    cost = value.get("cost_usd")
    return GatewayVideoResult(
        status=str(value["status"]),
        provider=str(value["provider"]),
        model=str(value["model"]),
        provider_request_id=value.get("provider_request_id"),
        output_ref=value.get("output_ref"),
        output_mime_type=value.get("output_mime_type"),
        cost_usd=None if cost is None else _decimal(cost),
        pricing_snapshot_id=value.get("pricing_snapshot_id"),
        routing_reason_codes=tuple(
            str(x) for x in value.get("routing_reason_codes", [])
        ),
        safety_metadata=dict(value.get("safety_metadata", {})),
        finish_reason=value.get("finish_reason"),
    )


def _encode_shot_runtime(runtime: ShotRuntime) -> dict[str, Any]:
    shot = runtime.compiled.shot
    return {
        "compiled": {
            "index": runtime.compiled.index,
            "shot_id": shot.shot_id,
            "paid_operation_id": runtime.compiled.paid_operation_id,
            "continuity_refs": list(runtime.compiled.continuity_refs),
            "retry_ordinal": runtime.compiled.retry_ordinal,
        },
        "status": runtime.status.value,
        "pending": (
            None
            if runtime.pending is None
            else {
                "shot_id": runtime.pending.shot_id,
                "operation_id": runtime.pending.operation_id,
                "capability": runtime.pending.capability,
                "queued_at_epoch": runtime.pending.queued_at_epoch,
                "result": _encode_result(runtime.pending.result),
            }
        ),
        "clip": (
            None
            if runtime.clip is None
            else {
                "shot_id": runtime.clip.shot_id,
                "object": _encode_object(runtime.clip.object),
                "checksum_sha256": runtime.clip.checksum_sha256,
                "probe": _encode_probe(runtime.clip.probe),
                "provider": runtime.clip.provider,
                "model": runtime.clip.model,
                "provider_request_id": runtime.clip.provider_request_id,
            }
        ),
        "validation": (
            None
            if runtime.validation is None
            else {
                "decision": runtime.validation.decision.value,
                "reason_codes": list(runtime.validation.reason_codes),
                "identity_checked": runtime.validation.identity_checked,
                "brand_checked": runtime.validation.brand_checked,
            }
        ),
        "actual_cost_usd": str(runtime.actual_cost_usd),
        "artifact_version_id": runtime.artifact_version_id,
        "error_code": runtime.error_code,
    }


def _decode_runtime(value: dict[str, Any], spec: VideoTaskSpec) -> ShotRuntime:
    compiled = value["compiled"]
    shot_id = str(compiled["shot_id"])
    shot = next(item for item in spec.shots if item.shot_id == shot_id)
    pending_value = value.get("pending")
    pending = None
    if pending_value is not None:
        pending = ProviderJobRecord(
            shot_id=str(pending_value["shot_id"]),
            operation_id=str(pending_value["operation_id"]),
            capability=str(pending_value["capability"]),
            queued_at_epoch=float(pending_value["queued_at_epoch"]),
            result=_decode_result(pending_value["result"]),
        )
    clip_value = value.get("clip")
    clip = None
    if clip_value is not None:
        clip = StoredVideoClip(
            shot_id=str(clip_value["shot_id"]),
            object=_object(clip_value["object"]),
            checksum_sha256=str(clip_value["checksum_sha256"]),
            probe=_probe(clip_value["probe"]),
            provider=str(clip_value["provider"]),
            model=str(clip_value["model"]),
            provider_request_id=str(clip_value["provider_request_id"]),
        )
    validation_value = value.get("validation")
    validation = None
    if validation_value is not None:
        validation = ShotValidationReport(
            decision=ValidationDecision(str(validation_value["decision"])),
            reason_codes=tuple(
                str(x) for x in validation_value.get("reason_codes", [])
            ),
            identity_checked=bool(validation_value["identity_checked"]),
            brand_checked=bool(validation_value["brand_checked"]),
        )
    return ShotRuntime(
        compiled=CompiledShot(
            index=int(compiled["index"]),
            shot=shot,
            paid_operation_id=str(compiled["paid_operation_id"]),
            continuity_refs=tuple(
                str(x) for x in compiled.get("continuity_refs", [])
            ),
            retry_ordinal=int(compiled.get("retry_ordinal", 0)),
        ),
        status=ShotStatus(str(value["status"])),
        pending=pending,
        clip=clip,
        validation=validation,
        actual_cost_usd=_decimal(value.get("actual_cost_usd", "0")),
        artifact_version_id=value.get("artifact_version_id"),
        error_code=value.get("error_code"),
    )


def _encode_provenance(value: FinalVideoProvenance) -> dict[str, Any]:
    return {
        "task_semantic_hash": value.task_semantic_hash,
        "source_shots": [
            {
                "shot_id": shot.shot_id,
                "operation_id": shot.operation_id,
                "retry_ordinal": shot.retry_ordinal,
                "provider": shot.provider,
                "model": shot.model,
                "provider_request_id": shot.provider_request_id,
                "source_asset_ids": list(shot.source_asset_ids),
                "identity_refs": list(shot.identity_refs),
                "rights_snapshot_ids": list(shot.rights_snapshot_ids),
                "cost_usd": str(shot.cost_usd),
                "artifact_version_id": shot.artifact_version_id,
            }
            for shot in value.source_shots
        ],
        "renderer_version": value.renderer_version,
        "brand_rule_snapshot_id": value.brand_rule_snapshot_id,
        "agent_run_id": value.agent_run_id,
        "agent_id": value.agent_id,
        "recipe_id": value.recipe_id,
        "skill_refs": list(value.skill_refs),
        "git_commit": value.git_commit,
    }


def _decode_provenance(value: dict[str, Any]) -> FinalVideoProvenance:
    return FinalVideoProvenance(
        task_semantic_hash=str(value["task_semantic_hash"]),
        source_shots=tuple(
            ShotProvenance(
                shot_id=str(item["shot_id"]),
                operation_id=str(item["operation_id"]),
                retry_ordinal=int(item["retry_ordinal"]),
                provider=str(item["provider"]),
                model=str(item["model"]),
                provider_request_id=str(item["provider_request_id"]),
                source_asset_ids=tuple(
                    str(x) for x in item.get("source_asset_ids", [])
                ),
                identity_refs=tuple(
                    str(x) for x in item.get("identity_refs", [])
                ),
                rights_snapshot_ids=tuple(
                    str(x) for x in item.get("rights_snapshot_ids", [])
                ),
                cost_usd=_decimal(item.get("cost_usd", "0")),
                artifact_version_id=item.get("artifact_version_id"),
            )
            for item in value.get("source_shots", [])
        ),
        renderer_version=str(value["renderer_version"]),
        brand_rule_snapshot_id=value.get("brand_rule_snapshot_id"),
        agent_run_id=value.get("agent_run_id"),
        agent_id=value.get("agent_id"),
        recipe_id=value.get("recipe_id"),
        skill_refs=tuple(str(x) for x in value.get("skill_refs", [])),
        git_commit=value.get("git_commit"),
    )


def encode_job(job: VideoJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "spec": encode_spec(job.spec),
        "status": job.status.value,
        "shots": [_encode_shot_runtime(item) for item in job.shots],
        "final_video": (
            None
            if job.final_video is None
            else {
                "object": _encode_object(job.final_video.object),
                "checksum_sha256": job.final_video.checksum_sha256,
                "probe": _encode_probe(job.final_video.probe),
                "renderer_version": job.final_video.renderer_version,
            }
        ),
        "provenance": (
            None if job.provenance is None else _encode_provenance(job.provenance)
        ),
        "final_artifact_version_id": job.final_artifact_version_id,
        "error_code": job.error_code,
    }


def decode_job(value: dict[str, Any]) -> VideoJob:
    spec = decode_spec(value["spec"])
    final_value = value.get("final_video")
    final_video = None
    if final_value is not None:
        final_video = RenderedVideo(
            object=_object(final_value["object"]),
            checksum_sha256=str(final_value["checksum_sha256"]),
            probe=_probe(final_value["probe"]),
            renderer_version=str(final_value["renderer_version"]),
        )
    provenance_value = value.get("provenance")
    return VideoJob(
        job_id=str(value["job_id"]),
        spec=spec,
        status=VideoJobStatus(str(value["status"])),
        shots=tuple(_decode_runtime(item, spec) for item in value["shots"]),
        final_video=final_video,
        provenance=(
            None
            if provenance_value is None
            else _decode_provenance(provenance_value)
        ),
        final_artifact_version_id=value.get("final_artifact_version_id"),
        error_code=value.get("error_code"),
    )
