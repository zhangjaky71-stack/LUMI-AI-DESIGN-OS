from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Protocol, cast

from .model import CompiledShot, RenderedVideo, ShotValidationReport, StoredVideoClip, ValidationDecision, ValidationFinding, VideoProbeResult, VideoTaskSpec, VideoTimeline


class IdentityContinuityPort(Protocol):
    async def validate_keyframes(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        keyframe_refs: tuple[str, ...],
    ) -> tuple[tuple[ValidationFinding, ...], str | None]: ...


class BrandContinuityPort(Protocol):
    async def validate_keyframes(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        keyframe_refs: tuple[str, ...],
    ) -> tuple[tuple[ValidationFinding, ...], str | None]: ...


def _technical_findings(spec: VideoTaskSpec, shot: CompiledShot, probe: VideoProbeResult) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    checks: tuple[tuple[bool, str, object, object], ...] = (
        (probe.decode_ok, "VIDEO_DECODE_FAILED", True, probe.decode_ok),
        (probe.mime_type == "video/mp4", "VIDEO_MIME_MISMATCH", "video/mp4", probe.mime_type),
        (probe.width == spec.width and probe.height == spec.height, "VIDEO_RESOLUTION_MISMATCH", (spec.width, spec.height), (probe.width, probe.height)),
        (abs(probe.fps - Decimal(spec.fps)) <= Decimal("0.01"), "VIDEO_FPS_MISMATCH", spec.fps, probe.fps),
        (abs(probe.duration_seconds - shot.shot.duration_seconds) <= Decimal("0.25"), "VIDEO_DURATION_MISMATCH", shot.shot.duration_seconds, probe.duration_seconds),
    )
    for passed, reason, expected, actual in checks:
        if not passed:
            findings.append(ValidationFinding(
                validator="video-technical",
                status="FAIL",
                severity="HARD",
                reason_code=reason,
                expected=expected,
                actual=actual,
            ))
    return findings


def _decision(findings: tuple[ValidationFinding, ...]) -> ValidationDecision:
    if any(item.severity == "HARD" and item.status != "PASS" for item in findings):
        return "REJECT"
    if any(item.status != "PASS" for item in findings):
        return "REPAIR"
    return "PASS"


class CompositeVideoValidator:
    def __init__(
        self,
        *,
        identity: IdentityContinuityPort | None = None,
        brand: BrandContinuityPort | None = None,
    ) -> None:
        self.identity = identity
        self.brand = brand

    async def validate_shot(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        clip: StoredVideoClip,
        probe: VideoProbeResult,
        safety_metadata: Mapping[str, object],
    ) -> ShotValidationReport:
        del clip
        findings = _technical_findings(spec, shot, probe)
        if safety_metadata.get("blocked") is True:
            findings.append(ValidationFinding(
                validator="model-gateway-safety",
                status="FAIL",
                severity="HARD",
                reason_code="VIDEO_PROVIDER_SAFETY_BLOCK",
            ))
        identity_snapshot: str | None = None
        brand_snapshot: str | None = None
        if spec.identity_requirements:
            if self.identity is None:
                findings.append(ValidationFinding(
                    validator="identity-engine",
                    status="UNAVAILABLE",
                    severity="HARD",
                    reason_code="VIDEO_IDENTITY_VALIDATOR_UNAVAILABLE",
                ))
            else:
                identity_findings, identity_snapshot = await self.identity.validate_keyframes(
                    spec=spec, shot=shot, keyframe_refs=probe.keyframe_refs
                )
                findings.extend(identity_findings)
        if spec.brand_rule_set_version is not None:
            if self.brand is None:
                findings.append(ValidationFinding(
                    validator="brand-rules",
                    status="UNAVAILABLE",
                    severity="HARD",
                    reason_code="VIDEO_BRAND_VALIDATOR_UNAVAILABLE",
                ))
            else:
                brand_findings, brand_snapshot = await self.brand.validate_keyframes(
                    spec=spec, shot=shot, keyframe_refs=probe.keyframe_refs
                )
                findings.extend(brand_findings)
        frozen = tuple(findings)
        return ShotValidationReport(
            decision=_decision(frozen),
            findings=frozen,
            identity_validation_snapshot_id=identity_snapshot,
            brand_validation_snapshot_id=brand_snapshot,
        )

    async def validate_final(
        self,
        *,
        spec: VideoTaskSpec,
        timeline: VideoTimeline,
        rendered: RenderedVideo,
    ) -> ShotValidationReport:
        findings: list[ValidationFinding] = []
        expected_seconds = sum((item.duration_seconds for item in timeline.clips), Decimal("0"))
        expected_ms = int(expected_seconds * Decimal("1000"))
        if abs(rendered.video.duration_ms - expected_ms) > 250:
            findings.append(ValidationFinding(
                validator="video-final",
                status="FAIL",
                severity="HARD",
                reason_code="VIDEO_FINAL_DURATION_MISMATCH",
                expected=expected_ms,
                actual=rendered.video.duration_ms,
            ))
        if rendered.video.width != spec.width or rendered.video.height != spec.height:
            findings.append(ValidationFinding(
                validator="video-final",
                status="FAIL",
                severity="HARD",
                reason_code="VIDEO_FINAL_RESOLUTION_MISMATCH",
            ))
        frozen = tuple(findings)
        return ShotValidationReport(decision=_decision(frozen), findings=frozen)
