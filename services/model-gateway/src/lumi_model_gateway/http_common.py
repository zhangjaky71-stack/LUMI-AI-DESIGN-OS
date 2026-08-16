from __future__ import annotations

import asyncio
import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .errors import ErrorCategory, ProviderAcceptance, ProviderCallError


@dataclass(frozen=True, slots=True)
class JsonHttpResponse:
    status: int
    headers: dict[str, str]
    body: dict[str, Any]


async def json_request(
    *,
    provider: str,
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 60,
) -> JsonHttpResponse:
    return await asyncio.to_thread(
        _json_request_sync,
        provider,
        method,
        url,
        headers,
        payload,
        timeout_seconds,
    )


def _json_request_sync(
    provider: str,
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout_seconds: float,
) -> JsonHttpResponse:
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            parsed = json.loads(raw) if raw else {}
            return JsonHttpResponse(
                status=int(response.status),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=parsed,
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        message = raw.decode("utf-8", "replace")[:2000] if raw else str(exc)
        raise normalize_http_error(provider, int(exc.code), message, dict(exc.headers.items())) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise ProviderCallError(
            ErrorCategory.TIMEOUT,
            f"{provider} request timeout/network failure: {type(exc).__name__}",
            provider=provider,
            retryable=True,
            acceptance=ProviderAcceptance.UNKNOWN,
        ) from exc


def normalize_http_error(
    provider: str, status: int, message: str, headers: dict[str, str] | None = None
) -> ProviderCallError:
    normalized_headers = {key.lower(): value for key, value in (headers or {}).items()}
    retry_after = _retry_after(normalized_headers.get("retry-after"))
    if status in {401, 403}:
        category = ErrorCategory.AUTH_ERROR
        retryable = False
    elif status == 429:
        category = ErrorCategory.RATE_LIMIT
        retryable = True
    elif status >= 500:
        category = ErrorCategory.PROVIDER_5XX
        retryable = True
    elif status in {408, 409, 425}:
        category = ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE
        retryable = True
    else:
        category = ErrorCategory.INVALID_REQUEST
        retryable = False
    return ProviderCallError(
        category,
        message[:2000],
        provider=provider,
        status_code=status,
        retry_after_seconds=retry_after,
        retryable=retryable,
        acceptance=ProviderAcceptance.NOT_ACCEPTED,
    )


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return max(0.0, min(seconds, 120.0))
