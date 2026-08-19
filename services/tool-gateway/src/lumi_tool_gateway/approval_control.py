from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .contracts import ApprovalDecision, ToolApproval, ToolDefinition, ToolRequest, canonical_json_bytes
from .errors import ToolApprovalControlUnavailableError
from .http_transport import sign_internal_request

_MAX_RESPONSE_BYTES = 512 * 1024
_DEFAULT_TIMEOUT_SECONDS = 15.0
_RESOLVE_PATH = "/internal/v1/tool-approval/resolve"


class HttpApprovalResolver:
    """Resolve high-risk Tool Gateway approvals through the canonical API control plane."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("TOOL_APPROVAL_URL_INVALID")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("TOOL_APPROVAL_URL_INVALID")
        if len(auth_secret) < 32 or len(auth_secret) > 8192 or "\x00" in auth_secret:
            raise ValueError("TOOL_APPROVAL_AUTH_SECRET_INVALID")
        if not 1.0 <= timeout_seconds <= 120.0:
            raise ValueError("TOOL_APPROVAL_TIMEOUT_INVALID")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> HttpApprovalResolver:
        return cls(
            base_url=os.getenv("LUMI_TOOL_APPROVAL_URL", ""),
            auth_secret=os.getenv("LUMI_TOOL_APPROVAL_AUTH_SECRET", ""),
        )

    async def resolve(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolApproval:
        payload = {
            "organization_id": str(request.organization_id),
            "agent_run_id": str(request.agent_run_id),
            "task_id": str(request.task_id),
            "tool_key": definition.key,
            "purpose": request.purpose,
            "arguments": request.arguments,
            "approval_id": request.approval_token,
        }
        response = await self._post(payload)
        decision_raw = str(response.get("decision") or "")
        approval_id = response.get("approval_id")
        reason_code = response.get("reason_code")
        if not isinstance(approval_id, str) or not approval_id:
            raise ToolApprovalControlUnavailableError(
                "canonical tool approval response has no approval id"
            )
        if reason_code is not None and not isinstance(reason_code, str):
            raise ToolApprovalControlUnavailableError(
                "canonical tool approval response has invalid reason code"
            )
        mapping = {
            "REQUIRED": ApprovalDecision.REQUIRED,
            "APPROVED": ApprovalDecision.APPROVED,
            "DENIED": ApprovalDecision.DENIED,
        }
        decision = mapping.get(decision_raw)
        if decision is None:
            raise ToolApprovalControlUnavailableError(
                f"unexpected canonical tool approval decision: {decision_raw or 'missing'}"
            )
        return ToolApproval(
            decision=decision,
            approval_id=approval_id,
            reason_code=reason_code,
        )

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = canonical_json_bytes(payload)
        auth = sign_internal_request(
            secret=self.auth_secret,
            service="tool-gateway",
            method="POST",
            path=_RESOLVE_PATH,
            body=body,
        )
        headers = {
            **auth.as_dict(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        return await asyncio.to_thread(self._post_sync, body, headers)

    def _post_sync(self, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{_RESOLVE_PATH}",
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
            raise ToolApprovalControlUnavailableError(
                "canonical tool approval control plane is unavailable"
            ) from exc
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ToolApprovalControlUnavailableError(
                "canonical tool approval response exceeded limit"
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ToolApprovalControlUnavailableError(
                "canonical tool approval control returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ToolApprovalControlUnavailableError(
                "canonical tool approval response must be an object"
            )
        if not 200 <= status < 300:
            code = str(payload.get("code") or "TOOL_APPROVAL_CONTROL_ERROR")
            message = str(payload.get("message") or "tool approval control request failed")
            raise ToolApprovalControlUnavailableError(f"{code}:{message}")
        return dict(payload)
