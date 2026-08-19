from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from .contracts import ToolAdapterOutput, ToolDefinition, ToolRequest, canonical_json_bytes
from .errors import ToolDataControlUnavailableError
from .http_transport import sign_internal_request

_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 15.0
_PROJECT_QUERY_PATH = "/internal/v1/tool-data/project/query"


class HttpToolDataClient:
    """Private Tool Gateway -> canonical API data control client."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("TOOL_DATA_URL_INVALID")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("TOOL_DATA_URL_INVALID")
        if len(auth_secret) < 32 or len(auth_secret) > 8192 or "\x00" in auth_secret:
            raise ValueError("TOOL_DATA_AUTH_SECRET_INVALID")
        if not 1.0 <= timeout_seconds <= 120.0:
            raise ValueError("TOOL_DATA_TIMEOUT_INVALID")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> HttpToolDataClient:
        return cls(
            base_url=os.getenv("LUMI_TOOL_DATA_URL", ""),
            auth_secret=os.getenv("LUMI_TOOL_DATA_AUTH_SECRET", ""),
        )

    async def project_query(self, request: ToolRequest) -> dict[str, Any]:
        raw_project_id = request.arguments.get("project_id")
        if not isinstance(raw_project_id, str):
            raise ToolDataControlUnavailableError("project query project_id is invalid")
        try:
            project_id = str(UUID(raw_project_id))
        except ValueError as exc:
            raise ToolDataControlUnavailableError("project query project_id is invalid") from exc
        return await self._post(
            _PROJECT_QUERY_PATH,
            {
                "organization_id": str(request.organization_id),
                "agent_run_id": str(request.agent_run_id),
                "task_id": str(request.task_id),
                "project_id": project_id,
            },
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = canonical_json_bytes(payload)
        auth = sign_internal_request(
            secret=self.auth_secret,
            service="tool-gateway",
            method="POST",
            path=path,
            body=body,
        )
        headers = {
            **auth.as_dict(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        return await asyncio.to_thread(self._post_sync, path, body, headers)

    def _post_sync(
        self,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
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
            raise ToolDataControlUnavailableError(
                "canonical Tool Data control plane is unavailable"
            ) from exc
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ToolDataControlUnavailableError(
                "canonical Tool Data response exceeded limit"
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ToolDataControlUnavailableError(
                "canonical Tool Data control returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ToolDataControlUnavailableError(
                "canonical Tool Data control response must be an object"
            )
        if not 200 <= status < 300:
            code = str(payload.get("code") or "TOOL_DATA_CONTROL_ERROR")
            message = str(payload.get("message") or "tool data request failed")
            raise ToolDataControlUnavailableError(f"{code}:{message}")
        return dict(payload)


class ProjectQueryAdapter:
    def __init__(self, client: HttpToolDataClient) -> None:
        self.client = client

    async def invoke(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolAdapterOutput:
        if definition.name != "project.query":
            raise ToolDataControlUnavailableError("project query adapter received wrong tool")
        data = await self.client.project_query(request)
        project_id = data.get("project_id")
        name = data.get("name")
        status = data.get("status")
        if not all(isinstance(value, str) and value for value in (project_id, name, status)):
            raise ToolDataControlUnavailableError(
                "canonical project query response is missing required fields"
            )
        return ToolAdapterOutput(
            data=data,
            summary=f"Project {name} is {status}.",
        )
