from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from .estimate_transport import HttpModelGatewayEstimateClient
from .http_transport import decode_model_result, sign_internal_request
from .models import ModelResult

ASYNC_STATUS_PATH = "/internal/v1/models/async/status"
ASYNC_CANCEL_PATH = "/internal/v1/models/async/cancel"
_MAX_IDENTIFIER = 512


@dataclass(frozen=True, slots=True)
class AsyncProviderControlRequest:
    provider: str
    model: str
    provider_request_id: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.provider, "PROVIDER"),
            (self.model, "MODEL"),
            (self.provider_request_id, "REQUEST_ID"),
        ):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > _MAX_IDENTIFIER
                or value != value.strip()
                or "\x00" in value
                or "\n" in value
                or "\r" in value
            ):
                raise ValueError(f"MODEL_GATEWAY_ASYNC_{label}_INVALID")

    def as_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model": self.model,
            "provider_request_id": self.provider_request_id,
        }


def decode_async_control_request(value: object) -> AsyncProviderControlRequest:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("MODEL_GATEWAY_ASYNC_REQUEST_OBJECT_REQUIRED")
    expected = {"provider", "model", "provider_request_id"}
    if set(value) != expected:
        raise ValueError("MODEL_GATEWAY_ASYNC_REQUEST_FIELDS_INVALID")
    return AsyncProviderControlRequest(
        provider=_required_string(value, "provider"),
        model=_required_string(value, "model"),
        provider_request_id=_required_string(value, "provider_request_id"),
    )


class HttpModelGatewayAsyncClient(HttpModelGatewayEstimateClient):
    """Signed provider-neutral async status/cancel client for internal callers."""

    async def get_async_status(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> ModelResult:
        return await self._control(
            ASYNC_STATUS_PATH,
            AsyncProviderControlRequest(provider, model, provider_request_id),
        )

    async def cancel(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
    ) -> ModelResult:
        return await self._control(
            ASYNC_CANCEL_PATH,
            AsyncProviderControlRequest(provider, model, provider_request_id),
        )

    async def _control(
        self,
        path: str,
        request: AsyncProviderControlRequest,
    ) -> ModelResult:
        body = json.dumps(
            request.as_dict(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        auth = sign_internal_request(
            secret=self.auth_secret,
            service=self.caller_service,
            method="POST",
            path=path,
            body=body,
        )
        payload = await asyncio.to_thread(
            self._request,
            path,
            body,
            auth.as_dict(),
        )
        return decode_model_result(payload)


def _required_string(value: dict[str, Any], key: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str):
        raise ValueError(f"MODEL_GATEWAY_ASYNC_{key.upper()}_INVALID")
    return candidate
