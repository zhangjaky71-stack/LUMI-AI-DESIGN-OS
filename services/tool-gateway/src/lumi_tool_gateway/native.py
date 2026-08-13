from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin

from .contracts import ToolAdapterOutput, ToolDefinition, ToolRequest
from .errors import (
    ToolRedirectLimitError,
    ToolResponseTooLargeError,
    ToolUnsupportedContentTypeError,
)
from .ssrf import SSRFPolicy


class NativeFunctionAdapter:
    def __init__(
        self,
        handler: Callable[[ToolDefinition, ToolRequest], Awaitable[ToolAdapterOutput]],
    ) -> None:
        self._handler = handler

    async def invoke(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolAdapterOutput:
        return await self._handler(definition, request)


class SearchBackend(Protocol):
    async def search(self, query: str, *, limit: int) -> list[dict[str, Any]]: ...


class WebSearchAdapter:
    def __init__(self, backend: SearchBackend) -> None:
        self.backend = backend

    async def invoke(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolAdapterOutput:
        del definition
        query = str(request.arguments["query"])
        limit = int(request.arguments.get("limit", 5))
        rows = await self.backend.search(query, limit=limit)
        normalized = [
            {
                "title": str(row.get("title", ""))[:500],
                "url": str(row.get("url", ""))[:4096],
                "snippet": str(row.get("snippet", ""))[:4000],
            }
            for row in rows[:limit]
        ]
        return ToolAdapterOutput(
            data={"results": normalized},
            summary=f"Found {len(normalized)} search results.",
        )


@dataclass(frozen=True, slots=True)
class HTTPTransportResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class PinnedHTTPTransport(Protocol):
    async def fetch(
        self,
        *,
        url: str,
        resolved_ip: str,
        host_header: str,
        timeout_seconds: float,
        max_bytes: int,
        headers: dict[str, str],
    ) -> HTTPTransportResponse: ...


class SafeWebFetchAdapter:
    _REDIRECTS = frozenset({301, 302, 303, 307, 308})

    def __init__(
        self,
        transport: PinnedHTTPTransport,
        *,
        ssrf_policy: SSRFPolicy | None = None,
        max_response_bytes: int = 2 * 1024 * 1024,
        max_redirects: int = 5,
        allowed_content_types: tuple[str, ...] = (
            "text/plain",
            "text/html",
            "application/json",
            "application/xhtml+xml",
        ),
    ) -> None:
        if not 1024 <= max_response_bytes <= 16 * 1024 * 1024:
            raise ValueError("TOOL_FETCH_RESPONSE_LIMIT_INVALID")
        if not 0 <= max_redirects <= 10:
            raise ValueError("TOOL_FETCH_REDIRECT_LIMIT_INVALID")
        self.transport = transport
        self.ssrf_policy = ssrf_policy or SSRFPolicy()
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self.allowed_content_types = allowed_content_types

    async def invoke(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolAdapterOutput:
        current_url = str(request.arguments["url"])
        redirects = 0
        while True:
            target = self.ssrf_policy.validate(current_url)
            response = await self.transport.fetch(
                url=target.url,
                resolved_ip=target.pinned_ip,
                host_header=target.hostname,
                timeout_seconds=min(definition.timeout_seconds, 30.0),
                max_bytes=self.max_response_bytes,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9",
                    "User-Agent": "LUMI-ToolGateway/1.0",
                },
            )
            if len(response.body) > self.max_response_bytes:
                raise ToolResponseTooLargeError("web response exceeds configured byte limit")
            if response.status in self._REDIRECTS:
                location = _header(response.headers, "location")
                if not location:
                    break
                redirects += 1
                if redirects > self.max_redirects:
                    raise ToolRedirectLimitError("web redirect limit exceeded")
                current_url = urljoin(current_url, location)
                continue
            content_type = _header(response.headers, "content-type").split(";", 1)[0].strip().lower()
            if content_type not in self.allowed_content_types:
                raise ToolUnsupportedContentTypeError(
                    f"blocked web content type: {content_type or 'unknown'}"
                )
            text = response.body.decode("utf-8", errors="replace")
            return ToolAdapterOutput(
                data={
                    "url": current_url,
                    "status": response.status,
                    "content_type": content_type,
                    "text": text,
                },
                summary=f"Fetched {current_url} ({response.status}).",
                resource_refs=(current_url,),
            )


class SandboxExecutor(Protocol):
    async def execute(
        self,
        *,
        organization_id: str,
        agent_run_id: str,
        task_id: str,
        command: list[str],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


class SandboxExecuteAdapter:
    """Narrow NODE-21 client port; never executes host shell commands itself."""

    def __init__(self, executor: SandboxExecutor) -> None:
        self.executor = executor

    async def invoke(
        self,
        definition: ToolDefinition,
        request: ToolRequest,
    ) -> ToolAdapterOutput:
        command = request.arguments.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) and item for item in command
        ):
            raise ValueError("TOOL_SANDBOX_COMMAND_INVALID")
        result = await self.executor.execute(
            organization_id=str(request.organization_id),
            agent_run_id=str(request.agent_run_id),
            task_id=str(request.task_id),
            command=list(command),
            timeout_seconds=definition.timeout_seconds,
        )
        return ToolAdapterOutput(
            data=result,
            summary="Sandbox command executed through isolated runtime.",
        )


def _header(headers: dict[str, str], name: str) -> str:
    name = name.lower()
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return ""
