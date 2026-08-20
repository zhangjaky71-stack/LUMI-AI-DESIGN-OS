from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

from lumi_video_generation.model import (
    GatewayVideoResult,
    ProviderJobRecord,
    ShotRuntime,
    ShotValidationReport,
    StoredVideoClip,
    ValidationFinding,
    VideoJob,
)
from lumi_video_generation.spec_codec import decode_spec, encode_spec

SNAPSHOT_SCHEMA_VERSION = 1
encode_video_task_spec = encode_spec
decode_video_task_spec = decode_spec


def encode_video_job(job: VideoJob) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "video_job_id": job.video_job_id,
        "organization_id": job.organization_id,
        "operation_id": job.operation_id,
        "semantic_hash": job.semantic_hash,
        "storyboard_hash": job.storyboard_hash,
        "status": job.status,
        "shots": [_encode_shot_runtime(value) for value in job.shots],
        "estimated_cost_usd": format(job.estimated_cost_usd, "f"),
        "actual_cost_usd": format(job.actual_cost_usd, "f"),
        "final_artifact_version_id": job.final_artifact_version_id,
        "error_code": job.error_code,
    }


def decode_video_job(value: object) -> VideoJob:
    payload = _object(value, "VIDEO_JOB_SNAPSHOT_OBJECT_REQUIRED")
    expected = {
        "schema_version",
        "video_job_id",
        "organization_id",
        "operation_id",
        "semantic_hash",
        "storyboard_hash",
        "status",
        "shots",
        "estimated_cost_usd",
        "actual_cost_usd",
        "final_artifact_version_id",
        "error_code",
    }
    _exact(payload, expected, "VIDEO_JOB_SNAPSHOT_FIELDS")
    if payload["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("VIDEO_JOB_SNAPSHOT_SCHEMA_UNSUPPORTED")
    status = _string(payload["status"], "VIDEO_JOB_STATUS_REQUIRED")
    if status not in {
        "SUBMITTING",
        "WAITING_EXTERNAL",
        "VALIDATING",
        "COMPOSING",
        "COMPLETED",
        "PARTIAL",
        "FAILED",
        "CANCELLED",
    }:
        raise ValueError("VIDEO_JOB_STATUS_INVALID")
    return VideoJob(
        video_job_id=_string(payload["video_job_id"], "VIDEO_JOB_ID_REQUIRED"),
        organization_id=_string(payload["organization_id"], "VIDEO_JOB_ORGANIZATION_REQUIRED"),
        operation_id=_string(payload["operation_id"], "VIDEO_JOB_OPERATION_REQUIRED"),
        semantic_hash=_sha256(payload["semantic_hash"], "VIDEO_JOB_SEMANTIC_HASH_INVALID"),
        storyboard_hash=_sha256(payload["storyboard_hash"], "VIDEO_JOB_STORYBOARD_HASH_INVALID"),
        status=cast(Any, status),
        shots=tuple(
            _decode_shot_runtime(item)
            for item in _list(payload["shots"], "VIDEO_JOB_SHOTS_INVALID")
        ),
        estimated_cost_usd=_decimal(payload["estimated_cost_usd"], "VIDEO_JOB_ESTIMATED_COST_INVALID"),
        actual_cost_usd=_decimal(payload["actual_cost_usd"], "VIDEO_JOB_ACTUAL_COST_INVALID"),
        final_artifact_version_id=_optional_string(
            payload["final_artifact_version_id"], "VIDEO_JOB_FINAL_ARTIFACT_INVALID"
        ),
        error_code=_optional_string(payload["error_code"], "VIDEO_JOB_ERROR_CODE_INVALID"),
    )


def encode_provider_record(record: ProviderJobRecord) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "organization_id": record.organization_id,
        "video_job_id": record.video_job_id,
        "shot_id": record.shot_id,
        "paid_operation_id": record.paid_operation_id,
        "request_hash": record.request_hash,
        "result": _encode_gateway_result(record.result),
    }


def decode_provider_record(value: object) -> ProviderJobRecord:
    payload = _object(value, "VIDEO_PROVIDER_SNAPSHOT_OBJECT_REQUIRED")
    expected = {
        "schema_version",
        "organization_id",
        "video_job_id",
        "shot_id",
        "paid_operation_id",
        "request_hash",
        "result",
    }
    _exact(payload, expected, "VIDEO_PROVIDER_SNAPSHOT_FIELDS")
    if payload["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("VIDEO_PROVIDER_SNAPSHOT_SCHEMA_UNSUPPORTED")
    return ProviderJobRecord(
        organization_id=_string(payload["organization_id"], "VIDEO_PROVIDER_ORGANIZATION_REQUIRED"),
        video_job_id=_string(payload["video_job_id"], "VIDEO_PROVIDER_JOB_ID_REQUIRED"),
        shot_id=_string(payload["shot_id"], "VIDEO_PROVIDER_SHOT_ID_REQUIRED"),
        paid_operation_id=_string(payload["paid_operation_id"], "VIDEO_PROVIDER_OPERATION_REQUIRED"),
        request_hash=_sha256(payload["request_hash"], "VIDEO_PROVIDER_REQUEST_HASH_INVALID"),
        result=_decode_gateway_result(payload["result"]),
    )


def _encode_gateway_result(result: GatewayVideoResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "provider": result.provider,
        "model": result.model,
        "provider_request_id": result.provider_request_id,
        "output_ref": result.output_ref,
        "output_mime_type": result.output_mime_type,
        "cost_usd": format(result.cost_usd, "f") if result.cost_usd is not None else None,
        "cost_confidence": result.cost_confidence,
        "pricing_snapshot_id": result.pricing_snapshot_id,
        "routing_reason_codes": list(result.routing_reason_codes),
        "safety_metadata": _json_object(dict(result.safety_metadata), "VIDEO_PROVIDER_SAFETY"),
        "finish_reason": result.finish_reason,
    }


def _decode_gateway_result(value: object) -> GatewayVideoResult:
    payload = _object(value, "VIDEO_GATEWAY_RESULT_OBJECT_REQUIRED")
    expected = {
        "status",
        "provider",
        "model",
        "provider_request_id",
        "output_ref",
        "output_mime_type",
        "cost_usd",
        "cost_confidence",
        "pricing_snapshot_id",
        "routing_reason_codes",
        "safety_metadata",
        "finish_reason",
    }
    _exact(payload, expected, "VIDEO_GATEWAY_RESULT_FIELDS")
    status = _string(payload["status"], "VIDEO_GATEWAY_STATUS_REQUIRED")
    if status not in {"PENDING", "SUCCEEDED", "FAILED", "CANCELLED"}:
        raise ValueError("VIDEO_GATEWAY_STATUS_INVALID")
    return GatewayVideoResult(
        status=cast(Any, status),
        provider=_string(payload["provider"], "VIDEO_GATEWAY_PROVIDER_REQUIRED"),
        model=_string(payload["model"], "VIDEO_GATEWAY_MODEL_REQUIRED"),
        provider_request_id=_optional_string(
            payload["provider_request_id"], "VIDEO_GATEWAY_REQUEST_ID_INVALID"
        ),
        output_ref=_optional_string(payload["output_ref"], "VIDEO_GATEWAY_OUTPUT_REF_INVALID"),
        output_mime_type=_optional_string(
            payload["output_mime_type"], "VIDEO_GATEWAY_OUTPUT_MIME_INVALID"
        ),
        cost_usd=(
            _decimal(payload["cost_usd"], "VIDEO_GATEWAY_COST_INVALID")
            if payload["cost_usd"] is not None
            else None
        ),
        cost_confidence=_string(payload["cost_confidence"], "VIDEO_GATEWAY_COST_CONFIDENCE_REQUIRED"),
        pricing_snapshot_id=_optional_string(
            payload["pricing_snapshot_id"], "VIDEO_GATEWAY_PRICING_SNAPSHOT_INVALID"
        ),
        routing_reason_codes=tuple(
            _string(item, "VIDEO_GATEWAY_REASON_INVALID")
            for item in _list(payload["routing_reason_codes"], "VIDEO_GATEWAY_REASONS_INVALID")
        ),
        safety_metadata=MappingProxyType(
            _json_object(payload["safety_metadata"], "VIDEO_PROVIDER_SAFETY")
        ),
        finish_reason=_optional_string(payload["finish_reason"], "VIDEO_GATEWAY_FINISH_REASON_INVALID"),
    )


def _encode_shot_runtime(value: ShotRuntime) -> dict[str, Any]:
    return {
        "shot_id": value.shot_id,
        "ordinal": value.ordinal,
        "paid_operation_id": value.paid_operation_id,
        "status": value.status,
        "attempt_count": value.attempt_count,
        "excluded_provider_keys": list(value.excluded_provider_keys),
        "provider": value.provider,
        "model": value.model,
        "provider_request_id": value.provider_request_id,
        "clip_artifact_version_id": value.clip_artifact_version_id,
        "attempt_artifact_version_ids": list(value.attempt_artifact_version_ids),
        "clip": _encode_clip(value.clip) if value.clip is not None else None,
        "validation": _encode_validation(value.validation) if value.validation is not None else None,
        "error_code": value.error_code,
    }


def _decode_shot_runtime(value: object) -> ShotRuntime:
    payload = _object(value, "VIDEO_SHOT_RUNTIME_OBJECT_REQUIRED")
    expected = {
        "shot_id",
        "ordinal",
        "paid_operation_id",
        "status",
        "attempt_count",
        "excluded_provider_keys",
        "provider",
        "model",
        "provider_request_id",
        "clip_artifact_version_id",
        "attempt_artifact_version_ids",
        "clip",
        "validation",
        "error_code",
    }
    _exact(payload, expected, "VIDEO_SHOT_RUNTIME_FIELDS")
    status = _string(payload["status"], "VIDEO_SHOT_RUNTIME_STATUS_REQUIRED")
    if status not in {"QUEUED", "WAITING_EXTERNAL", "READY", "FAILED", "DROPPED", "CANCELLED"}:
        raise ValueError("VIDEO_SHOT_RUNTIME_STATUS_INVALID")
    clip = payload["clip"]
    validation = payload["validation"]
    return ShotRuntime(
        shot_id=_string(payload["shot_id"], "VIDEO_SHOT_RUNTIME_ID_REQUIRED"),
        ordinal=_integer(payload["ordinal"], "VIDEO_SHOT_RUNTIME_ORDINAL_INVALID"),
        paid_operation_id=_string(
            payload["paid_operation_id"], "VIDEO_SHOT_RUNTIME_OPERATION_REQUIRED"
        ),
        status=cast(Any, status),
        attempt_count=_integer(payload["attempt_count"], "VIDEO_SHOT_RUNTIME_ATTEMPT_INVALID"),
        excluded_provider_keys=tuple(
            _string(item, "VIDEO_SHOT_RUNTIME_EXCLUSION_INVALID")
            for item in _list(
                payload["excluded_provider_keys"], "VIDEO_SHOT_RUNTIME_EXCLUSIONS_INVALID"
            )
        ),
        provider=_optional_string(payload["provider"], "VIDEO_SHOT_RUNTIME_PROVIDER_INVALID"),
        model=_optional_string(payload["model"], "VIDEO_SHOT_RUNTIME_MODEL_INVALID"),
        provider_request_id=_optional_string(
            payload["provider_request_id"], "VIDEO_SHOT_RUNTIME_REQUEST_ID_INVALID"
        ),
        clip_artifact_version_id=_optional_string(
            payload["clip_artifact_version_id"], "VIDEO_SHOT_RUNTIME_ARTIFACT_INVALID"
        ),
        attempt_artifact_version_ids=tuple(
            _string(item, "VIDEO_SHOT_RUNTIME_ATTEMPT_ARTIFACT_INVALID")
            for item in _list(
                payload["attempt_artifact_version_ids"],
                "VIDEO_SHOT_RUNTIME_ATTEMPT_ARTIFACTS_INVALID",
            )
        ),
        clip=_decode_clip(clip) if clip is not None else None,
        validation=_decode_validation(validation) if validation is not None else None,
        error_code=_optional_string(payload["error_code"], "VIDEO_SHOT_RUNTIME_ERROR_INVALID"),
    )


def _encode_clip(value: StoredVideoClip) -> dict[str, Any]:
    return {
        "storage_key": value.storage_key,
        "checksum_sha256": value.checksum_sha256,
        "mime_type": value.mime_type,
        "size_bytes": value.size_bytes,
        "width": value.width,
        "height": value.height,
        "duration_ms": value.duration_ms,
        "durable_asset_ref": value.durable_asset_ref,
        "poster_frame_ref": value.poster_frame_ref,
        "tail_frame_ref": value.tail_frame_ref,
        "keyframe_refs": list(value.keyframe_refs),
    }


def _decode_clip(value: object) -> StoredVideoClip:
    payload = _object(value, "VIDEO_CLIP_SNAPSHOT_OBJECT_REQUIRED")
    expected = {
        "storage_key",
        "checksum_sha256",
        "mime_type",
        "size_bytes",
        "width",
        "height",
        "duration_ms",
        "durable_asset_ref",
        "poster_frame_ref",
        "tail_frame_ref",
        "keyframe_refs",
    }
    _exact(payload, expected, "VIDEO_CLIP_SNAPSHOT_FIELDS")
    return StoredVideoClip(
        storage_key=_string(payload["storage_key"], "VIDEO_CLIP_STORAGE_KEY_REQUIRED"),
        checksum_sha256=_sha256(payload["checksum_sha256"], "VIDEO_CLIP_CHECKSUM_INVALID"),
        mime_type=_string(payload["mime_type"], "VIDEO_CLIP_MIME_REQUIRED"),
        size_bytes=_integer(payload["size_bytes"], "VIDEO_CLIP_SIZE_INVALID"),
        width=_integer(payload["width"], "VIDEO_CLIP_WIDTH_INVALID"),
        height=_integer(payload["height"], "VIDEO_CLIP_HEIGHT_INVALID"),
        duration_ms=_integer(payload["duration_ms"], "VIDEO_CLIP_DURATION_INVALID"),
        durable_asset_ref=_string(payload["durable_asset_ref"], "VIDEO_CLIP_ASSET_REF_REQUIRED"),
        poster_frame_ref=_optional_string(
            payload["poster_frame_ref"], "VIDEO_CLIP_POSTER_REF_INVALID"
        ),
        tail_frame_ref=_optional_string(payload["tail_frame_ref"], "VIDEO_CLIP_TAIL_REF_INVALID"),
        keyframe_refs=tuple(
            _string(item, "VIDEO_CLIP_KEYFRAME_INVALID")
            for item in _list(payload["keyframe_refs"], "VIDEO_CLIP_KEYFRAMES_INVALID")
        ),
    )


def _encode_validation(value: ShotValidationReport) -> dict[str, Any]:
    return {
        "decision": value.decision,
        "findings": [_encode_finding(item) for item in value.findings],
        "identity_validation_snapshot_id": value.identity_validation_snapshot_id,
        "brand_validation_snapshot_id": value.brand_validation_snapshot_id,
    }


def _decode_validation(value: object) -> ShotValidationReport:
    payload = _object(value, "VIDEO_VALIDATION_SNAPSHOT_OBJECT_REQUIRED")
    expected = {
        "decision",
        "findings",
        "identity_validation_snapshot_id",
        "brand_validation_snapshot_id",
    }
    _exact(payload, expected, "VIDEO_VALIDATION_SNAPSHOT_FIELDS")
    decision = _string(payload["decision"], "VIDEO_VALIDATION_DECISION_REQUIRED")
    if decision not in {"PASS", "REPAIR", "REJECT"}:
        raise ValueError("VIDEO_VALIDATION_DECISION_INVALID")
    return ShotValidationReport(
        decision=cast(Any, decision),
        findings=tuple(
            _decode_finding(item)
            for item in _list(payload["findings"], "VIDEO_VALIDATION_FINDINGS_INVALID")
        ),
        identity_validation_snapshot_id=_optional_string(
            payload["identity_validation_snapshot_id"],
            "VIDEO_VALIDATION_IDENTITY_SNAPSHOT_INVALID",
        ),
        brand_validation_snapshot_id=_optional_string(
            payload["brand_validation_snapshot_id"], "VIDEO_VALIDATION_BRAND_SNAPSHOT_INVALID"
        ),
    )


def _encode_finding(value: ValidationFinding) -> dict[str, Any]:
    return {
        "validator": value.validator,
        "status": value.status,
        "severity": value.severity,
        "reason_code": value.reason_code,
        "evidence_ref": value.evidence_ref,
        "expected": _json_value(value.expected, "VIDEO_FINDING_EXPECTED"),
        "actual": _json_value(value.actual, "VIDEO_FINDING_ACTUAL"),
    }


def _decode_finding(value: object) -> ValidationFinding:
    payload = _object(value, "VIDEO_FINDING_OBJECT_REQUIRED")
    expected_fields = {
        "validator",
        "status",
        "severity",
        "reason_code",
        "evidence_ref",
        "expected",
        "actual",
    }
    _exact(payload, expected_fields, "VIDEO_FINDING_FIELDS")
    status = _string(payload["status"], "VIDEO_FINDING_STATUS_REQUIRED")
    severity = _string(payload["severity"], "VIDEO_FINDING_SEVERITY_REQUIRED")
    if status not in {"PASS", "FAIL", "UNAVAILABLE"}:
        raise ValueError("VIDEO_FINDING_STATUS_INVALID")
    if severity not in {"HARD", "SOFT", "ADVISORY"}:
        raise ValueError("VIDEO_FINDING_SEVERITY_INVALID")
    return ValidationFinding(
        validator=_string(payload["validator"], "VIDEO_FINDING_VALIDATOR_REQUIRED"),
        status=cast(Any, status),
        severity=cast(Any, severity),
        reason_code=_string(payload["reason_code"], "VIDEO_FINDING_REASON_REQUIRED"),
        evidence_ref=_optional_string(payload["evidence_ref"], "VIDEO_FINDING_EVIDENCE_INVALID"),
        expected=_json_value(payload["expected"], "VIDEO_FINDING_EXPECTED"),
        actual=_json_value(payload["actual"], "VIDEO_FINDING_ACTUAL"),
    )


def _object(value: object, error: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(error)
    return value


def _exact(payload: dict[str, Any], expected: set[str], label: str) -> None:
    unknown = set(payload) - expected
    missing = expected - set(payload)
    if unknown:
        raise ValueError(f"{label}_UNKNOWN:{','.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{label}_MISSING:{','.join(sorted(missing))}")


def _string(value: object, error: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(error)
    return value


def _optional_string(value: object, error: str) -> str | None:
    if value is None:
        return None
    return _string(value, error)


def _integer(value: object, error: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error)
    return value


def _decimal(value: object, error: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(error)
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError(error) from exc
    if not result.is_finite():
        raise ValueError(error)
    return result


def _sha256(value: object, error: str) -> str:
    result = _string(value, error)
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise ValueError(error)
    return result


def _list(value: object, error: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(error)
    return value


def _json_object(value: object, label: str, *, depth: int = 0) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label}_OBJECT_REQUIRED")
    if depth > 12:
        raise ValueError(f"{label}_TOO_DEEP")
    return {key: _json_value(item, label, depth=depth + 1) for key, item in value.items()}


def _json_value(value: object, label: str, *, depth: int = 0) -> Any:
    if depth > 12:
        raise ValueError(f"{label}_TOO_DEEP")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(f"{label}_NON_FINITE")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{label}_NON_FINITE")
        return format(value, "f")
    if isinstance(value, dict):
        return _json_object(value, label, depth=depth + 1)
    if isinstance(value, (list, tuple)):
        return [_json_value(item, label, depth=depth + 1) for item in value]
    raise ValueError(f"{label}_VALUE_INVALID:{type(value).__name__}")
