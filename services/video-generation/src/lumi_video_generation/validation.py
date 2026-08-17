from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .model import (
    CompiledShot,
    GatewayVideoResult,
    ShotValidationReport,
    StoredVideoClip,
    ValidationDecision,
    VideoTaskSpec,
)


class IdentityValidationPort(Protocol):
    async def validate_video_identity(
        self,
        *,
        organization_id: str,
        project_id: str,
        clip_ref: str,
        identity_refs: tuple[str, ...],
    ) -> bool: ...


class BrandValidationPort(Protocol):
    async def validate_video_brand(
        self,
        *,
        organization_id: str,
        project_id: str,
        clip_ref: str,
        brand_rule_snapshot_id: str,
    ) -> bool: ...


@dataclass(slots=True)
class CompositeVideoValidator:
    identity: IdentityValidationPort | None = None
    brand: BrandValidationPort | None = None
    duration_tolerance_seconds: Decimal = Decimal("0.75")
    max_black_frame_ratio: Decimal = Decimal("0.15")

    async def validate(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        clip: StoredVideoClip,
        provider_result: GatewayVideoResult,
    ) -> ShotValidationReport:
        reasons: list[str] = []
        probe = clip.probe
        if provider_result.safety_metadata.get("hard_rejected") is True:
            reasons.append("PROVIDER_SAFETY_HARD_REJECT")
        if probe.mime_type not in {"video/mp4", "video/webm"}:
            reasons.append("VIDEO_CONTAINER_UNSUPPORTED")
        if probe.width != spec.width or probe.height != spec.height:
            reasons.append("VIDEO_DIMENSION_MISMATCH")
        if probe.decodable_frames <= 0:
            reasons.append("VIDEO_NO_DECODABLE_FRAMES")
        if abs(probe.duration_seconds - shot.shot.duration_seconds) > self.duration_tolerance_seconds:
            reasons.append("VIDEO_DURATION_MISMATCH")
        if probe.black_frame_ratio > self.max_black_frame_ratio:
            reasons.append("VIDEO_BLACK_FRAME_RATIO_EXCEEDED")

        identity_checked = not shot.shot.identity_refs
        if shot.shot.identity_refs:
            if self.identity is None:
                reasons.append("VIDEO_IDENTITY_VALIDATOR_REQUIRED")
            else:
                identity_checked = True
                if not await self.identity.validate_video_identity(
                    organization_id=spec.organization_id,
                    project_id=spec.project_id,
                    clip_ref=clip.durable_ref,
                    identity_refs=shot.shot.identity_refs,
                ):
                    reasons.append("VIDEO_IDENTITY_VALIDATION_FAILED")

        brand_checked = spec.brand_rule_snapshot_id is None
        if spec.brand_rule_snapshot_id is not None:
            if self.brand is None:
                reasons.append("VIDEO_BRAND_VALIDATOR_REQUIRED")
            else:
                brand_checked = True
                if not await self.brand.validate_video_brand(
                    organization_id=spec.organization_id,
                    project_id=spec.project_id,
                    clip_ref=clip.durable_ref,
                    brand_rule_snapshot_id=spec.brand_rule_snapshot_id,
                ):
                    reasons.append("VIDEO_BRAND_VALIDATION_FAILED")

        return ShotValidationReport(
            decision=(ValidationDecision.PASS if not reasons else ValidationDecision.REJECT),
            reason_codes=tuple(reasons),
            identity_checked=identity_checked,
            brand_checked=brand_checked,
        )
