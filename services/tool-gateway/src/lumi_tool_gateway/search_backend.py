from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

from .errors import ToolInputValidationError, ToolWebSearchUnavailableError

_BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_MAX_QUERY_CHARS = 400
_MAX_QUERY_WORDS = 50
_MAX_RESULTS = 20
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 12.0


class SearchProviderTransport(Protocol):
    async def search_json(self, *, query: str, count: int) -> dict[str, Any]: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


class BraveSearchHTTPTransport:
    """Fixed-origin Brave Search transport; provider credentials never follow redirects."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key or len(api_key) > 4096 or "\x00" in api_key:
            raise ValueError("LUMI_BRAVE_SEARCH_API_KEY_REQUIRED")
        if not 1.0 <= timeout_seconds <= 30.0:
            raise ValueError("BRAVE_SEARCH_TIMEOUT_INVALID")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> BraveSearchHTTPTransport:
        return cls(api_key=os.getenv("LUMI_BRAVE_SEARCH_API_KEY", ""))

    async def search_json(self, *, query: str, count: int) -> dict[str, Any]:
        return await asyncio.to_thread(self._search_sync, query=query, count=count)

    def _search_sync(self, *, query: str, count: int) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(
            {
                "q": query,
                "count": str(count),
                "result_filter": "web",
                "safesearch": "moderate",
                "text_decorations": "false",
            }
        )
        request = urllib.request.Request(
            f"{_BRAVE_SEARCH_ENDPOINT}?{encoded}",
            method="GET",
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "User-Agent": "LUMI-ToolGateway/1.0",
                "X-Subscription-Token": self._api_key,
            },
        )
        opener = urllib.request.build_opener(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=self._timeout_seconds) as response:
                status = int(response.status)
                content_type = str(response.headers.get("Content-Type", ""))
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise ToolWebSearchUnavailableError(
                f"Brave Search returned HTTP {int(exc.code)}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ToolWebSearchUnavailableError("Brave Search is unavailable") from exc
        if status != 200:
            raise ToolWebSearchUnavailableError(f"Brave Search returned HTTP {status}")
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ToolWebSearchUnavailableError("Brave Search response exceeded byte limit")
        if not content_type.lower().startswith("application/json"):
            raise ToolWebSearchUnavailableError("Brave Search returned non-JSON content")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ToolWebSearchUnavailableError("Brave Search returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ToolWebSearchUnavailableError("Brave Search response must be an object")
        return dict(payload)


class BraveSearchBackend:
    def __init__(self, transport: SearchProviderTransport) -> None:
        self._transport = transport

    @classmethod
    def from_env(cls) -> BraveSearchBackend:
        return cls(BraveSearchHTTPTransport.from_env())

    async def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        normalized = query.strip()
        if not normalized or len(normalized) > _MAX_QUERY_CHARS:
            raise ToolInputValidationError("web search query length is invalid")
        if len(normalized.split()) > _MAX_QUERY_WORDS:
            raise ToolInputValidationError("web search query exceeds provider word limit")
        if not 1 <= limit <= _MAX_RESULTS:
            raise ToolInputValidationError("web search result limit is invalid")

        payload = await self._transport.search_json(query=normalized, count=limit)
        web = payload.get("web")
        if web is None:
            return []
        if not isinstance(web, dict):
            raise ToolWebSearchUnavailableError("Brave Search web result envelope is invalid")
        rows = web.get("results", [])
        if not isinstance(rows, list):
            raise ToolWebSearchUnavailableError("Brave Search results must be an array")

        results: list[dict[str, Any]] = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            title = row.get("title")
            url = row.get("url")
            description = row.get("description", "")
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(url, str) or not _safe_result_url(url):
                continue
            snippet = description if isinstance(description, str) else ""
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                }
            )
        return results


def _safe_result_url(value: str) -> bool:
    if not value or len(value) > 4096 or "\x00" in value:
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    return bool(
        parsed.scheme.lower() in {"http", "https"}
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )
