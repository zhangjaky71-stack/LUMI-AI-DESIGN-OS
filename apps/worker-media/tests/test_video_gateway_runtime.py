from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import cast

import pytest
from lumi_model_gateway import HttpModelGatewayAsyncClient
from lumi_video_generation.model import CompiledShot, ShotSpec, VideoTaskSpec

from lumi_worker_media.video_gateway_runtime import HostedVideoGateway


def _shot(**changes: object) -> ShotSpec:
    base = ShotSpec(
        shot_id="hero",
        duration_seconds=Decimal("4"),
        prompt="A product rotates slowly in a clean studio",
    )
    return replace(base, **changes)


def _spec(*, shot: ShotSpec, **changes: object) -> VideoTaskSpec:
    base = VideoTaskSpec(
        organization_id="00000000-0000-0000-0000-000000000001",
        project_id="00000000-0000-0000-0000-000000000002",
        task_id="00000000-0000-0000-0000-000000000003",
        operation_id="00000000-0000-0000-0000-000000000004",
        mode="TEXT_TO_VIDEO",
        prompt=shot.prompt,
        duration_seconds=Decimal("4"),
        aspect_ratio="16:9",
        width=1280,
        height=720,
        fps=24,
        budget_limit_usd=Decimal("2.00"),
        code_git_sha="a" * 40,
        shots=(shot,),
    )
    return replace(base, **changes)


def _gateway() -> HostedVideoGateway:
    return HostedVideoGateway(
        client=cast(HttpModelGatewayAsyncClient, object()),
        model_profile="video-production",
    )


def _compiled(shot: ShotSpec) -> CompiledShot:
    return CompiledShot(
        shot=shot,
        paid_operation_id="00000000-0000-0000-0000-000000000005",
        ordinal=1,
    )


def test_hosted_video_request_binds_explicit_model_profile() -> None:
    shot = _shot()
    request = _gateway()._request(_spec(shot=shot), _compiled(shot), (), ())
    assert request.constraints["model_profile"] == "video-production"
    assert request.inputs["prompt"] == shot.prompt


@pytest.mark.parametrize(
    ("spec_changes", "shot_changes", "error"),
    [
        ({"negative_prompt": "no text"}, {}, "VIDEO_HOSTED_V1_NEGATIVE_PROMPT_UNSUPPORTED"),
        ({"seed": 7}, {}, "VIDEO_HOSTED_V1_SEED_UNSUPPORTED"),
        ({}, {"camera_motion": "dolly-in"}, "VIDEO_HOSTED_V1_CAMERA_MOTION_UNSUPPORTED"),
        ({}, {"subject_action": "turn left"}, "VIDEO_HOSTED_V1_SUBJECT_ACTION_UNSUPPORTED"),
    ],
)
def test_hosted_video_rejects_controls_not_supported_by_provider_create_api(
    spec_changes: dict[str, object],
    shot_changes: dict[str, object],
    error: str,
) -> None:
    shot = _shot(**shot_changes)
    spec = _spec(shot=shot, **spec_changes)
    with pytest.raises(ValueError, match=error):
        _gateway()._request(spec, _compiled(shot), (), ())


def test_hosted_video_profile_rejects_whitespace_or_shell_text() -> None:
    for profile in (" video-production", "video production", "video;production"):
        with pytest.raises(ValueError, match="VIDEO_MODEL_PROFILE_INVALID"):
            HostedVideoGateway(
                client=cast(HttpModelGatewayAsyncClient, object()),
                model_profile=profile,
            )
