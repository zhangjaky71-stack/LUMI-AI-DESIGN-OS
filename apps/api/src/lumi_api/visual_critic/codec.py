from __future__ import annotations

from typing import Any

from lumi_visual_critic.model import (
    DimensionAssessment,
    EvidenceKind,
    QualityDimension,
    QualityEvidence,
    QualityGateStatus,
    QualityProfileKey,
    QualityProfileSnapshot,
    QualityResult,
    QualitySeverity,
    QualityViolation,
    RepairAction,
    RepairActionType,
    GraderCalibrationSnapshot,
)


def encode_profile(value: QualityProfileSnapshot) -> dict[str, Any]:
    return {
        "profile_id": value.profile_id,
        "key": value.key.value,
        "version": value.version,
        "weights": {key.value: item for key, item in value.weights.items()},
        "thresholds": {key.value: item for key, item in value.thresholds.items()},
        "overall_pass_threshold": value.overall_pass_threshold,
        "warning_threshold": value.warning_threshold,
        "low_confidence_threshold": value.low_confidence_threshold,
        "hard_dimensions": sorted(item.value for item in value.hard_dimensions),
        "required_dimensions": sorted(item.value for item in value.required_dimensions),
        "visual_grader_required": value.visual_grader_required,
    }


def decode_profile(value: dict[str, Any]) -> QualityProfileSnapshot:
    return QualityProfileSnapshot(
        profile_id=str(value["profile_id"]),
        key=QualityProfileKey(str(value["key"])),
        version=int(value["version"]),
        weights={QualityDimension(str(key)): float(item) for key, item in value["weights"].items()},
        thresholds={QualityDimension(str(key)): float(item) for key, item in value["thresholds"].items()},
        overall_pass_threshold=float(value["overall_pass_threshold"]),
        warning_threshold=float(value["warning_threshold"]),
        low_confidence_threshold=float(value["low_confidence_threshold"]),
        hard_dimensions=frozenset(QualityDimension(str(item)) for item in value["hard_dimensions"]),
        required_dimensions=frozenset(QualityDimension(str(item)) for item in value["required_dimensions"]),
        visual_grader_required=bool(value["visual_grader_required"]),
    )


def encode_calibration(value: GraderCalibrationSnapshot) -> dict[str, Any]:
    return {
        "calibration_id": value.calibration_id,
        "grader_id": value.grader_id,
        "provider": value.provider,
        "model": value.model,
        "model_revision": value.model_revision,
        "dataset_hash": value.dataset_hash,
        "threshold_version": value.threshold_version,
        "sample_count": value.sample_count,
        "precision": value.precision,
        "recall": value.recall,
        "false_positive_rate": value.false_positive_rate,
        "false_negative_rate": value.false_negative_rate,
        "inter_rater_agreement": value.inter_rater_agreement,
    }


def decode_calibration(value: dict[str, Any]) -> GraderCalibrationSnapshot:
    return GraderCalibrationSnapshot(
        calibration_id=str(value["calibration_id"]),
        grader_id=str(value["grader_id"]),
        provider=value.get("provider"),
        model=value.get("model"),
        model_revision=value.get("model_revision"),
        dataset_hash=str(value["dataset_hash"]),
        threshold_version=int(value["threshold_version"]),
        sample_count=int(value["sample_count"]),
        precision=_optional_float(value.get("precision")),
        recall=_optional_float(value.get("recall")),
        false_positive_rate=_optional_float(value.get("false_positive_rate")),
        false_negative_rate=_optional_float(value.get("false_negative_rate")),
        inter_rater_agreement=_optional_float(value.get("inter_rater_agreement")),
    )


def encode_repair(value: RepairAction) -> dict[str, Any]:
    return {
        "action_type": value.action_type.value,
        "target": value.target,
        "reason_code": value.reason_code,
        "parameters": value.parameters,
        "expected_effect": [item.value for item in value.expected_effect],
    }


def decode_repair(value: dict[str, Any]) -> RepairAction:
    return RepairAction(
        action_type=RepairActionType(str(value["action_type"])),
        target=str(value["target"]),
        reason_code=str(value["reason_code"]),
        parameters=dict(value.get("parameters", {})),
        expected_effect=tuple(QualityDimension(str(item)) for item in value.get("expected_effect", [])),
    )


def encode_assessment(value: DimensionAssessment) -> dict[str, Any]:
    return {
        "dimension": value.dimension.value,
        "score": value.score,
        "confidence": value.confidence,
        "threshold": value.threshold,
        "severity": value.severity.value,
        "evidence_ids": list(value.evidence_ids),
        "grader_id": value.grader_id,
    }


def decode_assessment(value: dict[str, Any]) -> DimensionAssessment:
    return DimensionAssessment(
        dimension=QualityDimension(str(value["dimension"])),
        score=float(value["score"]),
        confidence=float(value["confidence"]),
        threshold=float(value["threshold"]),
        severity=QualitySeverity(str(value["severity"])),
        evidence_ids=tuple(str(item) for item in value.get("evidence_ids", [])),
        grader_id=value.get("grader_id"),
    )


def encode_violation(value: QualityViolation) -> dict[str, Any]:
    return {
        "violation_id": value.violation_id,
        "dimension": value.dimension.value,
        "code": value.code,
        "severity": value.severity.value,
        "message": value.message,
        "confidence": value.confidence,
        "blocking": value.blocking,
        "evidence_ids": list(value.evidence_ids),
        "repair_actions": [encode_repair(item) for item in value.repair_actions],
    }


def decode_violation(value: dict[str, Any]) -> QualityViolation:
    return QualityViolation(
        violation_id=str(value["violation_id"]),
        dimension=QualityDimension(str(value["dimension"])),
        code=str(value["code"]),
        severity=QualitySeverity(str(value["severity"])),
        message=str(value["message"]),
        confidence=float(value["confidence"]),
        blocking=bool(value["blocking"]),
        evidence_ids=tuple(str(item) for item in value.get("evidence_ids", [])),
        repair_actions=tuple(decode_repair(item) for item in value.get("repair_actions", [])),
    )


def encode_evidence(value: QualityEvidence) -> dict[str, Any]:
    return {
        "evidence_id": value.evidence_id,
        "kind": value.kind.value,
        "source_version": value.source_version,
        "summary": value.summary,
        "refs": list(value.refs),
        "data": value.data,
    }


def decode_evidence(value: dict[str, Any]) -> QualityEvidence:
    return QualityEvidence(
        evidence_id=str(value["evidence_id"]),
        kind=EvidenceKind(str(value["kind"])),
        source_version=str(value["source_version"]),
        summary=str(value["summary"]),
        refs=tuple(str(item) for item in value.get("refs", [])),
        data=dict(value.get("data", {})),
    )


def encode_result(value: QualityResult) -> dict[str, Any]:
    return {
        "quality_result_id": value.quality_result_id,
        "organization_id": value.organization_id,
        "project_id": value.project_id,
        "task_id": value.task_id,
        "operation_id": value.operation_id,
        "artifact_id": value.artifact_id,
        "artifact_version_id": value.artifact_version_id,
        "artifact_content_hash": value.artifact_content_hash,
        "profile_id": value.profile_id,
        "profile_version": value.profile_version,
        "profile_hash": value.profile_hash,
        "status": value.status.value,
        "overall_score": value.overall_score,
        "overall_confidence": value.overall_confidence,
        "assessments": [encode_assessment(item) for item in value.assessments],
        "violations": [encode_violation(item) for item in value.violations],
        "evidence": [encode_evidence(item) for item in value.evidence],
        "strengths": list(value.strengths),
        "repair_actions": [encode_repair(item) for item in value.repair_actions],
        "critic_grader_id": value.critic_grader_id,
        "critic_calibration_id": value.critic_calibration_id,
        "critic_calibration_hash": value.critic_calibration_hash,
        "reason_codes": list(value.reason_codes),
    }


def decode_result(value: dict[str, Any]) -> QualityResult:
    return QualityResult(
        quality_result_id=str(value["quality_result_id"]),
        organization_id=str(value["organization_id"]),
        project_id=str(value["project_id"]),
        task_id=str(value["task_id"]),
        operation_id=str(value["operation_id"]),
        artifact_id=str(value["artifact_id"]),
        artifact_version_id=str(value["artifact_version_id"]),
        artifact_content_hash=str(value["artifact_content_hash"]),
        profile_id=str(value["profile_id"]),
        profile_version=int(value["profile_version"]),
        profile_hash=str(value["profile_hash"]),
        status=QualityGateStatus(str(value["status"])),
        overall_score=float(value["overall_score"]),
        overall_confidence=float(value["overall_confidence"]),
        assessments=tuple(decode_assessment(item) for item in value.get("assessments", [])),
        violations=tuple(decode_violation(item) for item in value.get("violations", [])),
        evidence=tuple(decode_evidence(item) for item in value.get("evidence", [])),
        strengths=tuple(str(item) for item in value.get("strengths", [])),
        repair_actions=tuple(decode_repair(item) for item in value.get("repair_actions", [])),
        critic_grader_id=value.get("critic_grader_id"),
        critic_calibration_id=value.get("critic_calibration_id"),
        critic_calibration_hash=value.get("critic_calibration_hash"),
        reason_codes=tuple(str(item) for item in value.get("reason_codes", [])),
    )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
