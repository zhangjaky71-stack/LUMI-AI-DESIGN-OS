from __future__ import annotations

import asyncio
import json
from collections import deque
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from lumi_model_gateway.errors import ProviderInvocationError, ProviderValidationError
from lumi_model_gateway.models import Capability, ModelRequest, ResultStatus
from lumi_model_gateway.openai_adapter import HttpResponse
from lumi_model_gateway.openai_video_adapter import (
    OpenAIVideoGenerationAdapter,
    OpenAIVideoPriceCard,
    VideoDownloadResponse,
)

ORG = UUID("00000000-0000-0000-0000-000000000001")
OPERATION = UUID("00000000-0000-0000-0000-000000000002")


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        del headers, timeout_seconds
        payload = json.loads(body) if body is not None else None
        self.calls.append((method, url, payload))
        return self.responses.popleft()


class FakeContentTransport:
    def __init__(self, content: bytes = b"fake-mp4-payload") -> None:
        self.content = content
        self.calls: list[str] = []

    def download_to_path(
        self,
        *,
        url: str,
        headers: dict[str, str],
        path: Path,
        timeout_seconds: float,
        max_bytes: int,
    ) -> VideoDownloadResponse:
        del headers, timeout_seconds
        assert len(self.content) < max_bytes
        self.calls.append(url)
        path.write_bytes(self.content)
        return VideoDownloadResponse(
            status=200,
            headers={"content-type": "video/mp4", "content-length": str(len(self.content))},
        )


class FakeOutputStore:
    def __init__(self) -> None:
        self.async_calls: list[dict[str, object]] = []

    async def store_bytes(self, **kwargs: object) -> str:
        del kwargs
        raise AssertionError("video adapter must not use in-memory byte staging")

    async def store_path(self, **kwargs: object) -> str:
        del kwargs
        raise AssertionError("async recovery must not depend on original ModelRequest")

    async def store_async_path(self, **kwargs: object) -> str:
        path = kwargs["path"]
        assert isinstance(path, Path)
        assert path.read_bytes() == b"fake-mp4-payload"
        self.async_calls.append(dict(kwargs))
        return "s3://provider-output/provider-output/v1/async/video.mp4"


def _response(status: str) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={"x-request-id": "req-http"},
        body=json.dumps(
            {
                "id": "video_123",
                "status": status,
                "model": "sora-2",
                "seconds": "4",
                "size": "1280x720",
            }
        ).encode(),
    )


def _request(*, capability: Capability = Capability.VIDEO_TEXT_TO_VIDEO) -> ModelRequest:
    return ModelRequest(
        organization_id=ORG,
        operation_id=OPERATION,
        capability=capability,
        inputs={
            "prompt": "A restrained product film with soft camera movement",
            "duration_seconds": "4",
            "width": 1280,
            "height": 720,
        },
        constraints={
            "duration_seconds": "4",
            "width": 1280,
            "height": 720,
        },
    )


def _adapter(
    *,
    responses: list[HttpResponse],
) -> tuple[OpenAIVideoGenerationAdapter, FakeTransport, FakeContentTransport, FakeOutputStore]:
    transport = FakeTransport(responses)
    content = FakeContentTransport()
    store = FakeOutputStore()
    adapter = OpenAIVideoGenerationAdapter(
        api_key="test-key-not-real",
        model="sora-2",
        price_card=OpenAIVideoPriceCard(
            snapshot_id="video-price-test",
            usd_per_second_by_size={"1280x720": Decimal("0.10")},
        ),
        output_store=store,
        transport=transport,
        content_transport=content,
    )
    return adapter, transport, content, store


def test_create_poll_complete_stages_mp4_without_returning_binary() -> None:
    adapter, transport, content, store = _adapter(
        responses=[_response("queued"), _response("in_progress"), _response("completed")]
    )
    request = _request()

    estimate = asyncio.run(adapter.estimate_cost(request))
    assert estimate.amount_usd == Decimal("0.40")

    created = asyncio.run(adapter.invoke(request))
    assert created.status == ResultStatus.PENDING
    assert created.provider_request_id == "video_123"
    assert created.outputs == ()
    assert transport.calls[0] == (
        "POST",
        "https://api.openai.com/v1/videos",
        {
            "model": "sora-2",
            "prompt": "A restrained product film with soft camera movement",
            "seconds": "4",
            "size": "1280x720",
        },
    )

    pending = asyncio.run(adapter.get_async_status(provider_request_id="video_123"))
    assert pending.status == ResultStatus.PENDING
    assert pending.outputs == ()

    completed = asyncio.run(adapter.get_async_status(provider_request_id="video_123"))
    assert completed.status == ResultStatus.SUCCEEDED
    assert len(completed.outputs) == 1
    assert completed.outputs[0].kind == "asset_ref"
    assert completed.outputs[0].mime_type == "video/mp4"
    assert completed.outputs[0].value.startswith("s3://")
    assert content.calls == ["https://api.openai.com/v1/videos/video_123/content"]
    assert len(store.async_calls) == 1
    assert store.async_calls[0]["provider_request_id"] == "video_123"


def test_failed_provider_job_is_terminal_without_fake_output() -> None:
    adapter, _, content, store = _adapter(responses=[_response("failed")])
    result = asyncio.run(adapter.get_async_status(provider_request_id="video_123"))
    assert result.status == ResultStatus.FAILED
    assert result.outputs == ()
    assert content.calls == []
    assert store.async_calls == []


def test_image_to_video_and_unpriced_geometry_fail_closed() -> None:
    adapter, _, _, _ = _adapter(responses=[])
    with pytest.raises(ProviderValidationError):
        asyncio.run(adapter.estimate_cost(_request(capability=Capability.VIDEO_IMAGE_TO_VIDEO)))

    invalid = ModelRequest(
        organization_id=ORG,
        operation_id=OPERATION,
        capability=Capability.VIDEO_TEXT_TO_VIDEO,
        inputs={"prompt": "test", "duration_seconds": "4", "width": 1920, "height": 1080},
        constraints={"duration_seconds": "4", "width": 1920, "height": 1080},
    )
    with pytest.raises(ProviderValidationError):
        asyncio.run(adapter.estimate_cost(invalid))


def test_cancel_remains_fail_closed_until_provider_cancellation_is_proven() -> None:
    adapter, _, _, _ = _adapter(responses=[])
    with pytest.raises(ProviderInvocationError, match="does not equate deletion"):
        asyncio.run(adapter.cancel(provider_request_id="video_123"))
