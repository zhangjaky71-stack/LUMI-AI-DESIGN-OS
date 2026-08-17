from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from lumi_model_gateway.gateway import ModelGateway
from lumi_model_gateway.models import (
    Capability,
    InputKind,
    LatencyProfile,
    ModelInput,
    ModelRequest,
    QualityProfile,
    ResultStatus,
    RoutingHints,
)
from lumi_visual_critic.model import (
    ArtifactQualityInput,
    DimensionAssessment,
    EvidenceKind,
    QualityDimension,
    QualityEvidence,
    QualitySeverity,
    QualitySignalBundle,
    QualityTaskSpec,
    QualityViolation,
    RepairAction,
    RepairActionType,
    VisualGraderResult,
)


class CriticImageResolver(Protocol):
    async def resolve_ephemeral_uri(
        self,
        *,
        organization_id: str,
        project_id: str,
        primary_file_ref: str,
    ) -> str: ...


def _stable_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(NAMESPACE_URL, value)


_DIMENSIONS = {item.value: item for item in QualityDimension}
_SEVERITY = {item.value: item for item in QualitySeverity}
_REPAIRS = {item.value: item for item in RepairActionType}


_CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assessments", "violations", "strengths", "overall_confidence"],
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "score", "confidence", "severity", "evidence"],
                "properties": {
                    "dimension": {"type": "string", "enum": sorted(_DIMENSIONS)},
                    "score": {"type": "number", "minimum": 0, "maximum": 100},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "severity": {"type": "string", "enum": ["INFO", "WARNING", "ERROR"]},
                    "evidence": {"type": "string", "minLength": 1, "maxLength": 1000},
                },
            },
        },
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "code", "severity", "message", "confidence", "repair_actions"],
                "properties": {
                    "dimension": {"type": "string", "enum": sorted(_DIMENSIONS)},
                    "code": {"type": "string", "minLength": 1, "maxLength": 160},
                    "severity": {"type": "string", "enum": ["INFO", "WARNING", "ERROR"]},
                    "message": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "repair_actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["action_type", "target", "reason_code", "parameters"],
                            "properties": {
                                "action_type": {"type": "string", "enum": sorted(_REPAIRS)},
                                "target": {"type": "string", "minLength": 1, "maxLength": 200},
                                "reason_code": {"type": "string", "minLength": 1, "maxLength": 160},
                                "parameters": {"type": "object"},
                            },
                        },
                    },
                },
            },
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


class ModelGatewayVisualGraderAdapter:
    """Independent, calibration-pinned visual grader. It cannot emit HARD gates."""

    def __init__(
        self,
        gateway: ModelGateway,
        resolver: CriticImageResolver,
    ) -> None:
        self.gateway = gateway
        self.resolver = resolver

    async def grade(
        self,
        *,
        spec: QualityTaskSpec,
        artifact: ArtifactQualityInput,
        deterministic_signals: tuple[QualitySignalBundle, ...],
    ) -> VisualGraderResult:
        calibration = spec.critic_calibration
        if calibration is None or not calibration.provider or not calibration.model:
            raise ValueError("QUALITY_PINNED_CRITIC_CALIBRATION_REQUIRED")
        if (
            artifact.generation_provider == calibration.provider
            and artifact.generation_model == calibration.model
        ):
            raise ValueError("QUALITY_CRITIC_MODEL_ISOLATION_REQUIRED")
        uri = await self.resolver.resolve_ephemeral_uri(
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            primary_file_ref=artifact.primary_file_ref,
        )
        deterministic_summary = [
            {
                "source": bundle.source_id,
                "unavailable": bundle.unavailable_reason,
                "assessments": [
                    {
                        "dimension": item.dimension.value,
                        "score": item.score,
                        "confidence": item.confidence,
                    }
                    for item in bundle.assessments
                ],
                "violations": [
                    {
                        "dimension": item.dimension.value,
                        "code": item.code,
                        "severity": item.severity.value,
                        "blocking": item.blocking,
                    }
                    for item in bundle.violations
                ],
            }
            for bundle in deterministic_signals
        ]
        rubric = {
            "role": "independent_visual_quality_critic",
            "profile": spec.profile.key.value,
            "profile_version": spec.profile.version,
            "artifact_type": artifact.artifact_type,
            "deterministic_evidence": deterministic_summary,
            "rules": [
                "Never override deterministic hard failures.",
                "Judge observable visual quality only.",
                "Do not infer brand or identity facts absent from supplied evidence.",
                "Use only registered repair action types.",
                "Return calibrated numeric scores, not prose approval.",
            ],
        }
        request = ModelRequest(
            request_id=_stable_uuid(f"critic-request:{spec.operation_id}"),
            organization_id=_stable_uuid(spec.organization_id),
            project_id=_stable_uuid(spec.project_id),
            task_id=_stable_uuid(spec.task_id),
            operation_id=_stable_uuid(f"critic-operation:{spec.operation_id}"),
            capability=Capability.LLM_VISION,
            inputs=(
                ModelInput(
                    kind=InputKind.TEXT,
                    role="system",
                    text=json.dumps(rubric, sort_keys=True, separators=(",", ":")),
                ),
                ModelInput(
                    kind=InputKind.IMAGE,
                    role="user",
                    uri=uri,
                    media_type=str(artifact.metadata.get("mime_type") or "image/png"),
                ),
            ),
            quality_profile=QualityProfile.HIGH,
            latency_profile=LatencyProfile.STANDARD,
            structured_output_schema=_CRITIC_SCHEMA,
            constraints={
                "critic_calibration_id": calibration.calibration_id,
                "critic_dataset_hash": calibration.dataset_hash,
                "critic_threshold_version": calibration.threshold_version,
                "critic_model_revision": calibration.model_revision,
            },
            routing_hints=RoutingHints(
                preferred_providers=(calibration.provider,),
                preferred_models=(calibration.model,),
                excluded_providers=(
                    (artifact.generation_provider,)
                    if artifact.generation_provider
                    and artifact.generation_provider != calibration.provider
                    else ()
                ),
                allow_fallback=False,
                allow_unknown_cost=False,
            ),
        )
        result = await self.gateway.invoke(request)
        if result.status is not ResultStatus.COMPLETED:
            raise ValueError("QUALITY_CRITIC_MODEL_NOT_COMPLETED")
        if result.provider != calibration.provider or result.model != calibration.model:
            raise ValueError("QUALITY_CRITIC_CALIBRATION_MODEL_MISMATCH")
        if len(result.outputs) != 1:
            raise ValueError("QUALITY_CRITIC_OUTPUT_COUNT_INVALID")
        output = result.outputs[0]
        raw = output.json_value
        if raw is None and output.text:
            raw = json.loads(output.text)
        if not isinstance(raw, dict):
            raise ValueError("QUALITY_CRITIC_STRUCTURED_OUTPUT_REQUIRED")
        return self._parse(
            raw=raw,
            grader_id=calibration.grader_id,
            calibration_id=calibration.calibration_id,
            provider=result.provider,
            model=result.model,
        )

    @staticmethod
    def _parse(
        *,
        raw: dict[str, Any],
        grader_id: str,
        calibration_id: str,
        provider: str,
        model: str,
    ) -> VisualGraderResult:
        evidence: list[QualityEvidence] = []
        assessments: list[DimensionAssessment] = []
        for index, item in enumerate(raw.get("assessments", [])):
            dimension = _DIMENSIONS[str(item["dimension"])]
            evidence_id = f"critic:{calibration_id}:assessment:{index}"
            evidence.append(
                QualityEvidence(
                    evidence_id=evidence_id,
                    kind=EvidenceKind.VISUAL_GRADER,
                    source_version=f"{provider}/{model}:{calibration_id}",
                    summary=str(item["evidence"]),
                    refs=(calibration_id,),
                )
            )
            assessments.append(
                DimensionAssessment(
                    dimension=dimension,
                    score=float(item["score"]),
                    confidence=float(item["confidence"]),
                    threshold=0.0,
                    severity=_SEVERITY[str(item["severity"])] ,
                    evidence_ids=(evidence_id,),
                    grader_id=grader_id,
                )
            )
        violations: list[QualityViolation] = []
        for index, item in enumerate(raw.get("violations", [])):
            dimension = _DIMENSIONS[str(item["dimension"])]
            actions: list[RepairAction] = []
            for action in item.get("repair_actions", []):
                action_type = _REPAIRS[str(action["action_type"])]
                parameters = dict(action.get("parameters") or {})
                if action_type is RepairActionType.SET_PROPERTY and "property" not in parameters:
                    continue
                if action_type is RepairActionType.REPLACE_TEXT and "text" not in parameters:
                    continue
                actions.append(
                    RepairAction(
                        action_type=action_type,
                        target=str(action["target"]),
                        reason_code=str(action["reason_code"]),
                        parameters=parameters,
                        expected_effect=(dimension,),
                    )
                )
            evidence_id = f"critic:{calibration_id}:violation:{index}"
            evidence.append(
                QualityEvidence(
                    evidence_id=evidence_id,
                    kind=EvidenceKind.VISUAL_GRADER,
                    source_version=f"{provider}/{model}:{calibration_id}",
                    summary=str(item["message"]),
                    refs=(calibration_id,),
                )
            )
            violations.append(
                QualityViolation(
                    violation_id=evidence_id,
                    dimension=dimension,
                    code=str(item["code"]),
                    severity=_SEVERITY[str(item["severity"])],
                    message=str(item["message"]),
                    confidence=float(item["confidence"]),
                    blocking=False,
                    evidence_ids=(evidence_id,),
                    repair_actions=tuple(actions),
                )
            )
        return VisualGraderResult(
            grader_id=grader_id,
            calibration_id=calibration_id,
            assessments=tuple(assessments),
            violations=tuple(violations),
            evidence=tuple(evidence),
            strengths=tuple(str(item) for item in raw.get("strengths", [])),
            overall_confidence=float(raw["overall_confidence"]),
        )
