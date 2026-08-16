from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from lumi_api.idempotency.http_context import begin_request, end_request, was_replayed


class IdempotencyReplayMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        token = begin_request()
        try:
            response = await call_next(request)
            if was_replayed():
                response.headers["Idempotent-Replayed"] = "true"
            return response
        finally:
            end_request(token)
