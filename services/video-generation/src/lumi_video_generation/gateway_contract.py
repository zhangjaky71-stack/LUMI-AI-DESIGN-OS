from __future__ import annotations

import time

from .model import CompiledShot, GatewayVideoResult, ProviderJobRecord


VIDEO_TEXT_TO_VIDEO = "video.text_to_video"
VIDEO_IMAGE_TO_VIDEO = "video.image_to_video"


def video_capability(shot: CompiledShot) -> str:
    if shot.shot.source_ref is not None or shot.continuity_refs:
        return VIDEO_IMAGE_TO_VIDEO
    return VIDEO_TEXT_TO_VIDEO


def required_video_features(shot: CompiledShot) -> frozenset[str]:
    required = set(shot.shot.required_features)
    if shot.shot.source_ref is not None:
        required.add("video.start_frame")
    if shot.continuity_refs:
        required.add("video.reference_image")
    if shot.shot.camera_motion:
        required.add("video.camera_controls")
    return frozenset(required)


def pending_record(shot: CompiledShot, result: GatewayVideoResult) -> ProviderJobRecord:
    return ProviderJobRecord(
        shot_id=shot.shot.shot_id,
        operation_id=shot.paid_operation_id,
        capability=video_capability(shot),
        queued_at_epoch=time.time(),
        result=result,
    )
