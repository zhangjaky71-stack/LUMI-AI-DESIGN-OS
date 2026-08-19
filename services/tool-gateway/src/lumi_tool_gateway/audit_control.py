from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .audit import ToolAuditRecord
from .contracts import canonical_json_bytes
from .errors import ToolAuditUnavailableError
from .http_transport import sign_internal_request

_AUDIT_PATH = "/internal/v1/tool-audit/events"
_MAX_RESPONSE_BYTES = 256 * 1024
_DEFAULT_TIMEOUT_SECONDS = 10.0


class HttpAuditSink:
    """Durable Tool Gateway audit sink backed by the canonical API `audit_events` store."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("TOOL_AUDIT_URL_INVALID")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("TOOL_AUDIT_URL_INVALID")
        if len(auth_secret) < 32 or len(auth_secret) > 8192 or "\x00" in auth_secret:
            raise ValueError("TOOL_AUDIT_AUTH_SECRET_INVALID")
        if not 1.0 <= timeout_seconds <= 120.0:
            raise ValueError("TOOL_AUDIT_TIMEOUT_INVALID")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> HttpAuditSink:
        return cls(
            base_url=os.getenv("LUMI_TOOL_AUDIT_URL", ""),
            auth_secret=os.getenv("LUMI_TOOL_AUDIT_AUTH_SECRET", ""),
        )

    async def record(self, event: ToolAuditRecord) -> None:
        body = canonical_json_bytes(
            {
                "event_id": event.event_id,
                "tool_call_id": event.tool_call_id,
                "organization_id": event.organization_id,
                "actor_id": event.actor_id,
                "actor_agent": event.actor_agent,
                "resolved_tool": event.resolved_tool,
                "risk": event.risk,
                "purpose": event.purpose,
                "status": event.status,
                "trace_id": event.trace_id,
                "arguments": event.arguments,
                "replayed": event.replayed,
                "side_effect_operation_id": event.side_effect_operation_id,
                "approval_id": event.approval_id,
                "error_code": event.error_code,
            }
        )
        headers = sign_internal_request(
            secret=self.auth_secret,
            service="tool-gateway",
            method="POST",
            path=_AUDIT_PATH,
            body=body,
        ).as_dict()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        last_error: Exception | None = None
        for _ in range(2):
            try:
                await asyncio.to_thread(self._post_sync, body, headers)
                return
            except ToolAuditUnavailableError as exc:
                last_error = exc
        raise ToolAuditUnavailableError(
            "canonical Tool Gateway audit could not be durably committed"
        ) from last_error

    def _post_sync(self, body: bytes, headers: dict[str, str]) -> None:
        request = urllib.request.Request(
            f"{self.base_url}{_AUDIT_PATH}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raw = exc.read(_MAX_RESPONSE_BYTES + 1)
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ToolAuditUnavailableError("canonical audit endpoint is unavailable") from exc

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ToolAuditUnavailableError("canonical audit response exceeded limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ToolAuditUnavailableError("canonical audit returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ToolAuditUnavailableError("canonical audit response must be an object")
        if not 200 <= status < 300:
            code = str(payload.get("code") or "TOOL_AUDIT_HTTP_ERROR")[:128]
            message = str(payload.get("message") or "canonical audit request failed")[:2000]
            raise ToolAuditUnavailableError(f"{code}:{message}")
        if str(payload.get("event_id") or "") == "":
            raise ToolAuditUnavailableError("canonical audit response omitted event id")
