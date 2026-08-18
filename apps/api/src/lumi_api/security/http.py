from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from lumi_api.domain.ids import new_uuid7

HTTP_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
}

_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "passwd",
        "client_secret",
        "session_secret",
        "private_key",
        "card_number",
        "cvc",
        "cvv",
    }
)


class SecurityHTTPMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        *,
        environment: str = "development",
        max_json_bytes: int = 2_097_152,
    ) -> None:
        super().__init__(app)
        if max_json_bytes < 1024:
            raise ValueError("SECURITY_JSON_LIMIT_TOO_SMALL")
        self.environment = environment.strip().casefold()
        self.max_json_bytes = max_json_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        query_problem = self._query_problem(request)
        if query_problem is not None:
            return self._with_headers(query_problem)

        size_problem = self._size_problem(request)
        if size_problem is not None:
            return self._with_headers(size_problem)

        response = await call_next(request)
        return self._with_headers(response)

    def _query_problem(self, request: Request) -> JSONResponse | None:
        raw_query = request.scope.get("query_string", b"")
        try:
            pairs = parse_qsl(
                raw_query.decode("utf-8", "strict"),
                keep_blank_values=True,
                strict_parsing=False,
                max_num_fields=256,
            )
        except (UnicodeDecodeError, ValueError):
            return self._problem(
                request,
                status=400,
                code="security_query_invalid",
                title="Invalid query string",
                detail="The query string could not be safely parsed.",
            )
        for key, _ in pairs:
            normalized = key.strip().casefold().replace("-", "_").replace(".", "_")
            if normalized in _SENSITIVE_QUERY_KEYS:
                return self._problem(
                    request,
                    status=400,
                    code="security_sensitive_query_forbidden",
                    title="Sensitive query parameter forbidden",
                    detail="Credentials and secrets must be supplied through an approved authenticated channel, never a URL query parameter.",
                )
        return None

    def _size_problem(self, request: Request) -> JSONResponse | None:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        is_json = content_type == "application/json" or content_type.endswith("+json")
        if not is_json:
            return None
        raw_length = request.headers.get("content-length")
        if raw_length is None:
            # App-level enforcement cannot prove a limit for chunked/streamed bodies.
            # The ingress/proxy streamed-body gate remains an explicit NODE-66 P0.
            return None
        try:
            content_length = int(raw_length)
        except ValueError:
            return self._problem(
                request,
                status=400,
                code="security_content_length_invalid",
                title="Invalid Content-Length",
                detail="Content-Length must be a non-negative integer.",
            )
        if content_length < 0:
            return self._problem(
                request,
                status=400,
                code="security_content_length_invalid",
                title="Invalid Content-Length",
                detail="Content-Length must be a non-negative integer.",
            )
        if content_length > self.max_json_bytes:
            return self._problem(
                request,
                status=413,
                code="security_json_body_too_large",
                title="Request body too large",
                detail="The JSON request body exceeds the application security limit.",
            )
        return None

    def _with_headers(self, response: Any) -> Any:
        for key, value in HTTP_SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if self.environment == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
        return response

    @staticmethod
    def _problem(
        request: Request,
        *,
        status: int,
        code: str,
        title: str,
        detail: str,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(new_uuid7()))
        return JSONResponse(
            status_code=status,
            media_type="application/problem+json",
            headers={"X-Request-ID": request_id},
            content={
                "type": "about:blank",
                "title": title,
                "status": status,
                "detail": detail,
                "code": code,
                "request_id": request_id,
                "instance": str(request.url.path),
            },
        )


def install_http_security(
    app: FastAPI,
    *,
    environment: str | None = None,
    max_json_bytes: int = 2_097_152,
) -> None:
    app.add_middleware(
        SecurityHTTPMiddleware,
        environment=environment or os.getenv("LUMI_ENV", "development"),
        max_json_bytes=max_json_bytes,
    )
