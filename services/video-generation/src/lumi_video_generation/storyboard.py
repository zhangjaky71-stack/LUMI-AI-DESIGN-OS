from __future__ import annotations

from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from .model import CompiledShot, ShotSpec, VideoTaskSpec


def shot_operation_id(root_operation_id: str, shot_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"lumi:video:{root_operation_id}:shot:{shot_id}:attempt:0"))


def retry_shot_operation_id(root_operation_id: str, shot_id: str, retry_ordinal: int) -> str:
    if retry_ordinal < 1:
        raise ValueError("retry_ordinal must be >= 1")
    return str(
        uuid5(
            NAMESPACE_URL,
            f"lumi:video:{root_operation_id}:shot:{shot_id}:attempt:{retry_ordinal}",
        )
    )


def compile_storyboard(spec: VideoTaskSpec) -> tuple[CompiledShot, ...]:
    compiled: list[CompiledShot] = []
    previous_source: str | None = None
    for index, shot in enumerate(spec.shots):
        continuity: tuple[str, ...] = ()
        if previous_source is not None:
            continuity = (previous_source,)
        compiled.append(
            CompiledShot(
                index=index,
                shot=shot,
                paid_operation_id=shot_operation_id(spec.operation_id, shot.shot_id),
                continuity_refs=continuity,
            )
        )
        if shot.source_ref is not None:
            previous_source = shot.source_ref.durable_ref
    return tuple(compiled)


def compile_retry(spec: VideoTaskSpec, previous: CompiledShot) -> CompiledShot:
    retry_ordinal = previous.retry_ordinal + 1
    return replace(
        previous,
        paid_operation_id=retry_shot_operation_id(
            spec.operation_id,
            previous.shot.shot_id,
            retry_ordinal,
        ),
        retry_ordinal=retry_ordinal,
    )


def source_assets(shot: ShotSpec) -> tuple[str, ...]:
    if shot.source_ref is None:
        return ()
    return (shot.source_ref.asset_id,)
