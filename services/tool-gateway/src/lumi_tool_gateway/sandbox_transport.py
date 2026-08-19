from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .contracts import canonical_json_bytes

_EXECUTE_PATH = "/internal/v1/sandbox/execute"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class SandboxRuntimeTransportError(RuntimeError):
    pass


class HttpSandboxExecutor:
    """NODE-25 -> NODE-21 private executor; never invokes a host shell locally."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        timeout_seconds: float = 130.0,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("SANDBOX_RUNTIME_URL_INVALID")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("SANDBOX_RUNTIME_URL_INVALID")
        if len(auth_secret) < 32 or len(auth_secret) > 8192 or "\x00" in auth_secret:
            raise ValueError("SANDBOX_RUNTIME_AUTH_SECRET_INVALID")
        if not 1.0 <= timeout_seconds <= 3600.0:
            raise ValueError("SANDBOX_RUNTIME_TIMEOUT_INVALID")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> HttpSandboxExecutor:
        return cls(
            base_url=os.getenv("LUMI_SANDBOX_RUNTIME_URL", ""),
            auth_secret=os.getenv("LUMI_SANDBOX_RUNTIME_AUTH_SECRET", ""),
        )

    async def execute(
        self,
        *,
        organization_id: str,
        agent_run_id: str,
        task_id: str,
        command: list[str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        timeout = max(1, min(3600, math.ceil(timeout_seconds)))
        body = canonical_json_bytes(
            {
                "organization_id": organization_id,
                "agent_run_id": agent_run_id,
                "task_id": task_id,
                "command": command,
                "timeout_seconds": timeout,
            }
        )
        timestamp = int(time.time())
        signature = hmac.new(
            self.auth_secret.encode("utf-8"),
            _auth_message("tool-gateway", timestamp, "POST", _EXECUTE_PATH, body),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Lumi-Service": "tool-gateway",
            "X-Lumi-Timestamp": str(timestamp),
            "X-Lumi-Signature": signature,
        }
        return await asyncio.to_thread(self._post, body, headers)

    def _post(self, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{_EXECUTE_PATH}",
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
            raise SandboxRuntimeTransportError("SANDBOX_RUNTIME_UNAVAILABLE") from exc
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise SandboxRuntimeTransportError("SANDBOX_RUNTIME_RESPONSE_TOO_LARGE")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SandboxRuntimeTransportError("SANDBOX_RUNTIME_RESPONSE_INVALID") from exc
        if not isinstance(payload, dict):
            raise SandboxRuntimeTransportError("SANDBOX_RUNTIME_RESPONSE_INVALID")
        if not 200 <= status < 300:
            code = payload.get("code")
            if not isinstance(code, str) or not code:
                code = "SANDBOX_RUNTIME_HTTP_ERROR"
            raise SandboxRuntimeTransportError(code[:128])
        return payload


def _auth_message(service: str, timestamp: int, method: str, path: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{service}\n{timestamp}\n{method.upper()}\n{path}\n{body_hash}".encode("utf-8")
