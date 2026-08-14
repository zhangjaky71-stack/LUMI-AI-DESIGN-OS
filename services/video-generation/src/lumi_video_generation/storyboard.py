from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from .model import CompiledShot, CompiledStoryboard, ShotSpec, SourceImageRef, VideoTaskSpec


def _stable_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(NAMESPACE_URL, value)


def shot_operation_id(root_operation_id: str, shot_id: str) -> str:
    return str(uuid5(_stable_uuid(root_operation_id), f"video-shot:{shot_id}"))


def compile_storyboard(spec: VideoTaskSpec) -> CompiledStoryboard:
    if spec.shots:
        shots = spec.shots
    else:
        source: SourceImageRef | None = spec.source_images[0] if spec.source_images else None
        shots = (
            ShotSpec(
                shot_id="shot-001",
                duration_seconds=spec.duration_seconds,
                prompt=spec.prompt,
                source_ref=source,
            ),
        )
    ids = [shot.shot_id for shot in shots]
    if len(ids) != len(set(ids)):
        raise ValueError("VIDEO_SHOT_ID_DUPLICATE")
    total = sum((shot.duration_seconds for shot in shots), Decimal("0"))
    if total != spec.duration_seconds:
        raise ValueError("VIDEO_STORYBOARD_DURATION_MISMATCH")
    compiled = tuple(
        CompiledShot(
            shot=shot,
            paid_operation_id=shot_operation_id(spec.operation_id, shot.shot_id),
            ordinal=index,
        )
        for index, shot in enumerate(shots, start=1)
    )
    payload = [
        {
            "shot_id": item.shot.shot_id,
            "duration": format(item.shot.duration_seconds, "f"),
            "prompt": item.shot.prompt,
            "camera": item.shot.camera_motion,
            "action": item.shot.subject_action,
            "transition": item.shot.transition_to_next,
            "optional": item.shot.optional,
            "paid_operation_id": item.paid_operation_id,
        }
        for item in compiled
    ]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CompiledStoryboard(shots=compiled, total_duration_seconds=total, storyboard_hash=digest)


def previous_ready_clip_ref(
    storyboard: CompiledStoryboard,
    shot_id: str,
    clip_tail_refs: dict[str, str],
) -> str | None:
    index = next((idx for idx, item in enumerate(storyboard.shots) if item.shot.shot_id == shot_id), None)
    if index is None or index == 0:
        return None
    previous_id = storyboard.shots[index - 1].shot.shot_id
    return clip_tail_refs.get(previous_id)
