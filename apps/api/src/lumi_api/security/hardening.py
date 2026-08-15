from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    """Controls owned by the public HTTP perimeter only.

    Canonical security ownership intentionally lives elsewhere for deeper boundaries:
    Tool Gateway owns SSRF/outbound fetch policy, Asset Storage owns uploaded media
    validation/sanitization, Agent Context Engine owns untrusted prompt context, and
    Project Core/Tool Gateway own approval/authorization for sensitive actions.
    """

    max_request_bytes: int = 8 * 1024 * 1024
    production: bool = False


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}\b"),
)
_SENSITIVE_QUERY_KEYS = frozenset(
    {"access_token", "api_key", "apikey", "token", "password", "secret"}
)


def redact_secrets(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def apply_security_hardening(app: FastAPI, config: SecurityConfig) -> None:
    """Install source-level HTTP release controls on every public FastAPI app.

    The application-side request limit is an early guard based on Content-Length.
    Production ingress/proxy configuration must independently enforce the same or a
    stricter body-size limit so chunked/streamed requests fail before expensive work.
    """

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                parsed_length = int(content_length)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "invalid content-length"})
            if parsed_length < 0:
                return JSONResponse(status_code=400, content={"detail": "invalid content-length"})
            if parsed_length > config.max_request_bytes:
                return JSONResponse(status_code=413, content={"detail": "request too large"})

        query_keys = {key.lower() for key in request.query_params.keys()}
        if query_keys.intersection(_SENSITIVE_QUERY_KEYS):
            return JSONResponse(
                status_code=400,
                content={"detail": "sensitive credentials are forbidden in URL query"},
            )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        if config.production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
