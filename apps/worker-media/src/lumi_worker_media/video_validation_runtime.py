from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from lumi_video_generation import CompositeVideoValidator
from lumi_video_generation.model import (
    CompiledShot,
    ShotValidationReport,
    StoredVideoClip,
    ValidationFinding,
    VideoProbeResult,
    VideoTaskSpec,
)


class HostedV1VideoValidator(CompositeVideoValidator):
    """Hosted V1 validation with provider/raw and final-output responsibilities split.

    The hosted OpenAI Videos create contract does not expose an FPS control. Raw
    provider clips therefore must not be rejected merely because their observed FPS
    differs from the requested final output FPS. The typed ffmpeg composition owns
    FPS normalization and HostedVerifiedVideoMediaSandbox independently ffprobes the
    promoted final MP4 before Artifact readiness.

    Raw-shot acceptance remains fail-closed for properties the provider response must
    satisfy before composition: decodability, MP4 MIME, requested geometry, requested
    duration, and provider safety status.
    """

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
        findings: list[ValidationFinding] = []
        checks: tuple[tuple[bool, str, object, object], ...] = (
            (probe.decode_ok, "VIDEO_DECODE_FAILED", True, probe.decode_ok),
            (
                probe.mime_type == "video/mp4",
                "VIDEO_MIME_MISMATCH",
                "video/mp4",
                probe.mime_type,
            ),
            (
                probe.width == spec.width and probe.height == spec.height,
                "VIDEO_RESOLUTION_MISMATCH",
                (spec.width, spec.height),
                (probe.width, probe.height),
            ),
            (
                abs(probe.duration_seconds - shot.shot.duration_seconds) <= Decimal("0.25"),
                "VIDEO_DURATION_MISMATCH",
                shot.shot.duration_seconds,
                probe.duration_seconds,
            ),
        )
        for passed, reason, expected, actual in checks:
            if not passed:
                findings.append(
                    ValidationFinding(
                        validator="hosted-video-raw",
                        status="FAIL",
                        severity="HARD",
                        reason_code=reason,
                        expected=expected,
                        actual=actual,
                    )
                )
        if safety_metadata.get("blocked") is True:
            findings.append(
                ValidationFinding(
                    validator="model-gateway-safety",
                    status="FAIL",
                    severity="HARD",
                    reason_code="VIDEO_PROVIDER_SAFETY_BLOCK",
                )
            )
        frozen = tuple(findings)
        return ShotValidationReport(
            decision="REJECT" if frozen else "PASS",
            findings=frozen,
        )


__all__ = ["HostedV1VideoValidator"]
