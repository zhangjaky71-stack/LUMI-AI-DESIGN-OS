from __future__ import annotations

import asyncio
from typing import Any

import pytest

from lumi_api.visual_critic.model_gateway_adapter import (
    ModelGatewayVisualGraderAdapter,
)
from lumi_model_gateway.models import (
    Capability,
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelRequest,
    NormalizedResult,
    ResultStatus,
)
from lumi_visual_critic import (
    ArtifactQualityInput,
    GraderCalibrationSnapshot,
    QualityProfileKey,
    QualityTaskSpec,
    get_builtin_profile,
)


class Gateway:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.request: ModelRequest | None = None

    async def invoke(self, request: ModelRequest) -> NormalizedResult:
        self.request = request
        return NormalizedResult(
            status=ResultStatus.COMPLETED,
            provider="critic-provider",
            model="critic-model-v2",
            outputs=(
                ModelOutput(kind="json", json_value=self.raw),
            ),
            provider_request_id="req-critic-1",
            cost=CostEstimate(None, CostConfidence.UNKNOWN),
        )


class Resolver:
    async def resolve_ephemeral_uri(self, **kwargs: Any) -> str:
        return "asset://ephemeral/quality-input"


def task() -> QualityTaskSpec:
    return QualityTaskSpec(
        organization_id="org",
        project_id="project",
        task_id="task",
        operation_id="operation",
        artifact_version_id="version",
        profile=get_builtin_profile(
            QualityProfileKey.PRODUCTION_WEB
        ),
        requested_by="user",
        critic_calibration=GraderCalibrationSnapshot(
            calibration_id="cal-v2",
            grader_id="visual-grader-v2",
            provider="critic-provider",
            model="critic-model-v2",
            model_revision="2026-08-01",
            dataset_hash="a" * 64,
            threshold_version=2,
            sample_count=1000,
            precision=0.93,
            recall=0.90,
        ),
    )


def artifact() -> ArtifactQualityInput:
    return ArtifactQualityInput(
        organization_id="org",
        project_id="project",
        artifact_id="artifact",
        artifact_version_id="version",
        artifact_type="IMAGE",
        content_hash="b" * 64,
        primary_file_ref="bucket:key",
        metadata={"mime_type": "image/png"},
        generation_provider="generator-provider",
        generation_model="generator-model-v5",
    )


def valid_raw() -> dict[str, Any]:
    return {
        "assessments": [
            {
                "dimension": "composition",
                "score": 88,
                "confidence": 0.91,
                "severity": "INFO",
                "evidence": (
                    "Balanced main subject and supporting elements"
                ),
            }
        ],
        "violations": [],
        "strengths": ["clear focal point"],
        "overall_confidence": 0.91,
    }


def test_critic_is_pinned_to_calibrated_vision_model_without_fallback():
    async def scenario() -> None:
        gateway = Gateway(valid_raw())
        adapter = ModelGatewayVisualGraderAdapter(
            gateway,  # type: ignore[arg-type]
            Resolver(),
        )
        result = await adapter.grade(
            spec=task(),
            artifact=artifact(),
            deterministic_signals=(),
        )
        request = gateway.request
        assert request is not None
        assert request.capability is Capability.LLM_VISION
        assert request.routing_hints.preferred_providers == (
            "critic-provider",
        )
        assert request.routing_hints.preferred_models == (
            "critic-model-v2",
        )
        assert request.routing_hints.allow_fallback is False
        assert result.calibration_id == "cal-v2"
        assert result.assessments[0].score == 88

    asyncio.run(scenario())


def test_visual_model_cannot_emit_hard_gate():
    async def scenario() -> None:
        raw = valid_raw()
        raw["violations"] = [
            {
                "dimension": "composition",
                "code": "SUBJECTIVE_HARD",
                "severity": "HARD",
                "message": "model tried to hard block",
                "confidence": 0.9,
                "repair_actions": [],
            }
        ]
        gateway = Gateway(raw)
        adapter = ModelGatewayVisualGraderAdapter(
            gateway,  # type: ignore[arg-type]
            Resolver(),
        )
        with pytest.raises(
            ValueError,
            match="QUALITY_HARD_VIOLATION_MUST_BLOCK",
        ):
            await adapter.grade(
                spec=task(),
                artifact=artifact(),
                deterministic_signals=(),
            )

    asyncio.run(scenario())
