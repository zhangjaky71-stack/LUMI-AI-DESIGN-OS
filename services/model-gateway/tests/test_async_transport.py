from __future__ import annotations

import asyncio
import json

import pytest

from lumi_model_gateway.async_transport import (
    ASYNC_CANCEL_PATH,
    ASYNC_STATUS_PATH,
    HttpModelGatewayAsyncClient,
    decode_async_control_request,
)


class FakeAsyncClient(HttpModelGatewayAsyncClient):
    def __init__(self) -> None:
        super().__init__(
            base_url="http://model-gateway.internal",
            auth_secret="s" * 32,
            caller_service="worker-media",
        )
        self.calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

    def _request(
        self,
        path: str,
        body: bytes,
        auth_headers: dict[str, str],
    ) -> dict[str, object]:
        self.calls.append((path, json.loads(body.decode("utf-8")), auth_headers))
        return {
            "status": "PENDING",
            "provider": "provider-a",
            "model": "video-a",
            "provider_request_id": "provider-job-123",
            "outputs": [],
            "usage": {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "cached_input_tokens": None,
                "image_input_tokens": None,
                "image_output_tokens": None,
                "seconds": None,
                "units": {},
            },
            "timing": {"total_ms": 5, "ttft_ms": None, "queue_ms": None},
            "cost": {
                "amount_usd": "0.01000000",
                "confidence": "EXACT",
                "price_snapshot_id": "price-v1",
                "detail": {},
            },
            "safety_metadata": {},
            "finish_reason": None,
            "raw_response_ref": None,
        }


def test_async_status_and_cancel_use_signed_provider_neutral_paths() -> None:
    client = FakeAsyncClient()

    status = asyncio.run(
        client.get_async_status(
            provider="provider-a",
            model="video-a",
            provider_request_id="provider-job-123",
        )
    )
    cancelled = asyncio.run(
        client.cancel(
            provider="provider-a",
            model="video-a",
            provider_request_id="provider-job-123",
        )
    )

    assert status.provider == "provider-a"
    assert cancelled.model == "video-a"
    assert [call[0] for call in client.calls] == [ASYNC_STATUS_PATH, ASYNC_CANCEL_PATH]
    for _, payload, headers in client.calls:
        assert payload == {
            "model": "video-a",
            "provider": "provider-a",
            "provider_request_id": "provider-job-123",
        }
        assert headers["X-Lumi-Service"] == "worker-media"
        assert len(headers["X-Lumi-Signature"]) == 64


def test_async_control_request_rejects_unknown_fields_and_dirty_identifiers() -> None:
    with pytest.raises(ValueError, match="MODEL_GATEWAY_ASYNC_REQUEST_FIELDS_INVALID"):
        decode_async_control_request(
            {
                "provider": "provider-a",
                "model": "video-a",
                "provider_request_id": "job-1",
                "provider_api_key": "forbidden",
            }
        )

    with pytest.raises(ValueError, match="MODEL_GATEWAY_ASYNC_REQUEST_ID_INVALID"):
        decode_async_control_request(
            {
                "provider": "provider-a",
                "model": "video-a",
                "provider_request_id": " job-1 ",
            }
        )
