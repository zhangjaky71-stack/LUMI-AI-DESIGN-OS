from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from typing import Iterable
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class SecurityViolation(ValueError):
    pass


class ToolRisk(StrEnum):
    READ = "read"
    EXTERNAL_READ = "external_read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    max_request_bytes: int = 8 * 1024 * 1024
    max_upload_bytes: int = 100 * 1024 * 1024
    production: bool = False
    allowed_origins: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExternalContent:
    text: str
    trust: str = "external_untrusted"
    executable_instructions: bool = False


_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}\b"),
)
_ALLOWED_UPLOAD_MIME_PREFIXES = ("image/", "video/", "audio/", "text/")
_ALLOWED_UPLOAD_MIMES = {"application/pdf", "application/json", "application/zip"}


def _is_forbidden_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return any(
        (
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def assert_safe_outbound_url(url: str, *, resolved_ips: Iterable[str] | None = None) -> str:
    """Fail closed for outbound HTTP(S). Re-run this guard after every redirect."""
    decoded = unquote(url).strip()
    parsed = urlsplit(decoded)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SecurityViolation("outbound URL must be absolute http(s)")
    if parsed.username or parsed.password:
        raise SecurityViolation("userinfo in outbound URL is forbidden")

    host = parsed.hostname.rstrip(".").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise SecurityViolation("local/metadata host is forbidden")

    candidates: set[str] = set(resolved_ips or ())
    try:
        candidates.add(str(ipaddress.ip_address(host)))
    except ValueError:
        if resolved_ips is None:
            try:
                for result in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
                    candidates.add(result[4][0])
            except socket.gaierror as exc:
                raise SecurityViolation("hostname resolution failed") from exc

    if not candidates:
        raise SecurityViolation("hostname did not resolve")
    for address in candidates:
        if _is_forbidden_ip(address):
            raise SecurityViolation("private/local network destination is forbidden")
    return decoded


def sanitize_upload_filename(filename: str) -> str:
    normalized = filename.replace("\\", "/").replace("\x00", "").strip()
    name = PurePath(normalized).name
    if not name or name in {".", ".."} or name != normalized:
        raise SecurityViolation("unsafe upload filename")
    if any(ord(char) < 32 for char in name):
        raise SecurityViolation("control character in upload filename")
    return name[:255]


def validate_upload_metadata(*, filename: str, content_type: str, size: int, max_bytes: int) -> str:
    safe_name = sanitize_upload_filename(filename)
    if size < 0 or size > max_bytes:
        raise SecurityViolation("upload size limit exceeded")
    mime = content_type.split(";", 1)[0].strip().lower()
    if not (mime in _ALLOWED_UPLOAD_MIMES or mime.startswith(_ALLOWED_UPLOAD_MIME_PREFIXES)):
        raise SecurityViolation("upload MIME type is not allowed")
    if mime == "image/svg+xml":
        raise SecurityViolation("raw SVG uploads require isolated sanitization")
    return safe_name


def classify_external_content(text: str) -> ExternalContent:
    """External text is data only. It never upgrades authorization or tool permissions."""
    return ExternalContent(text=text, trust="external_untrusted", executable_instructions=False)


def require_tool_approval(risk: ToolRisk, *, approved: bool) -> None:
    if risk in {ToolRisk.DESTRUCTIVE, ToolRisk.PRIVILEGED} and not approved:
        raise SecurityViolation("human approval required for sensitive tool")


def redact_secrets(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def apply_security_hardening(app: FastAPI, config: SecurityConfig) -> None:
    """Install release-gate HTTP controls on every public FastAPI app."""

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > config.max_request_bytes:
                    return JSONResponse(status_code=413, content={"detail": "request too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "invalid content-length"})

        if request.url.query:
            lowered = request.url.query.lower()
            if any(token in lowered for token in ("access_token=", "api_key=", "apikey=", "token=", "password=")):
                return JSONResponse(status_code=400, content={"detail": "sensitive credentials are forbidden in URL query"})

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if config.production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
