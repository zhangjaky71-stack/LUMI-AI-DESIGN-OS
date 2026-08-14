from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal

from lumi_model_gateway import (
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    MockProvider,
    ModelGateway,
    ModelRequest,
    ModelResult,
    ModelRouter,
    RetryPolicy,
)

from lumi_video_generation.media_sandbox import FfmpegArgvCompiler
from lumi_video_generation.model import (
    TimelineAudioTrack,
    TimelineClip,
    VideoOutputSpec,
    VideoTimeline,
)
from lumi_video_generation.model_gateway_adapter import ModelGatewayVideoAdapter
from lumi_video_generation.storyboard import compile_storyboard
from test_video_generation import _spec


class PassthroughPaidGuard:
    async def execute(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        invoke: Callable[[], Awaitable[ModelResult]],
    ) -> ModelResult:
        del request, provider, model
        return await invoke()


def _gateway() -> ModelGateway:
    p1 = MockProvider(provider="p1", model="video-a", quality_score=95)
    p2 = MockProvider(provider="p2", model="video-b", quality_score=90)
    registry = InMemoryProviderRegistry((p1, p2))
    health = InMemoryProviderHealthRegistry(failure_threshold=2)
    return ModelGateway(
        registry=registry,
        health=health,
        router=ModelRouter(registry=registry, health=health),
        paid_guard=PassthroughPaidGuard(),
        retry_policy=RetryPolicy(
            max_attempts_per_provider=1,
            base_delay_seconds=0,
            max_delay_seconds=0,
            max_elapsed_seconds=1,
        ),
    )


def test_request_provider_exclusion_routes_retry_to_second_provider() -> None:
    spec = _spec()
    shot = compile_storyboard(spec).shots[0]
    result = asyncio.run(
        ModelGatewayVideoAdapter(_gateway()).submit(
            spec=spec,
            shot=shot,
            continuity_refs=(),
            excluded_provider_keys=("p1:video-a",),
        )
    )
    assert result.status == "PENDING"
    assert result.provider == "p2"
    assert "VIDEO_EXCLUDED_PROVIDERS:1" in result.routing_reason_codes


class Resolver:
    def resolve_readonly(self, durable_ref: str) -> str:
        token = durable_ref.replace(":", "-")
        return f"/sandbox/input/{token}"

    def allocate_output(self, suffix: str) -> str:
        return "/sandbox/output/final" + suffix


def test_multi_track_audio_is_compiled_as_typed_delay_gain_and_amix() -> None:
    timeline = VideoTimeline(
        clips=(TimelineClip(
            shot_id="s1",
            artifact_version_id="v1",
            durable_ref="asset:video:v1",
            duration_seconds=Decimal("3"),
        ),),
        overlays=(),
        audio_tracks=(
            TimelineAudioTrack("asset:audio:music", Decimal("0"), Decimal("-6")),
            TimelineAudioTrack("asset:audio:voice", Decimal("0.5"), Decimal("0")),
        ),
        transitions=(),
        output_spec=VideoOutputSpec(width=1600, height=900, fps=24),
    )
    invocation = FfmpegArgvCompiler().compile(timeline, Resolver())
    filter_complex = invocation.argv[invocation.argv.index("-filter_complex") + 1]
    assert "volume=-6dB,adelay=0:all=1[aud0]" in filter_complex
    assert "volume=0dB,adelay=500:all=1[aud1]" in filter_complex
    assert "[aud0][aud1]amix=inputs=2" in filter_complex
    assert "-t" in invocation.argv
    assert invocation.argv[invocation.argv.index("-t") + 1] == "3"
