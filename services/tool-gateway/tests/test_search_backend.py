from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

from lumi_tool_gateway.errors import ToolInputValidationError
from lumi_tool_gateway.search_backend import (
    BraveSearchBackend,
    BraveSearchHTTPTransport,
    _NoRedirectHandler,
)


class _FakeProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, int]] = []

    async def search_json(self, *, query: str, count: int) -> dict[str, Any]:
        self.calls.append((query, count))
        return self.payload


class _Headers:
    def get(self, name: str, default: str = "") -> str:
        return "application/json" if name.lower() == "content-type" else default


class _Response:
    status = 200
    headers = _Headers()

    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: Any) -> None:
        del args

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


class _Opener:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[Any] = []

    def open(self, request: Any, *, timeout: float) -> _Response:
        self.requests.append((request, timeout))
        return _Response(self.payload)


class BraveSearchBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_backend_normalizes_only_http_results(self) -> None:
        provider = _FakeProvider(
            {
                "web": {
                    "results": [
                        {
                            "title": "One",
                            "url": "https://example.com/one",
                            "description": "First result",
                        },
                        {
                            "title": "Blocked",
                            "url": "ftp://example.com/file",
                            "description": "Not web",
                        },
                        {
                            "title": "Two",
                            "url": "http://example.org/two",
                            "description": "Second result",
                        },
                    ]
                }
            }
        )
        backend = BraveSearchBackend(provider)
        results = await backend.search("design systems", limit=3)

        self.assertEqual(provider.calls, [("design systems", 3)])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["snippet"], "First result")
        self.assertTrue(results[0]["url"].startswith("https://"))
        self.assertTrue(results[1]["url"].startswith("http://"))

    async def test_provider_limits_fail_before_network(self) -> None:
        provider = _FakeProvider({})
        backend = BraveSearchBackend(provider)
        with self.assertRaises(ToolInputValidationError):
            await backend.search("x" * 401, limit=5)
        with self.assertRaises(ToolInputValidationError):
            await backend.search(" ".join(["word"] * 51), limit=5)
        with self.assertRaises(ToolInputValidationError):
            await backend.search("valid", limit=21)
        self.assertEqual(provider.calls, [])

    async def test_http_transport_uses_fixed_origin_and_subscription_header(self) -> None:
        opener = _Opener({"web": {"results": []}})
        transport = BraveSearchHTTPTransport(api_key="provider-secret")
        with patch(
            "lumi_tool_gateway.search_backend.urllib.request.build_opener",
            return_value=opener,
        ) as build_opener:
            payload = await transport.search_json(query="lumi design", count=5)

        self.assertEqual(payload, {"web": {"results": []}})
        self.assertEqual(len(opener.requests), 1)
        request, timeout = opener.requests[0]
        self.assertTrue(
            request.full_url.startswith(
                "https://api.search.brave.com/res/v1/web/search?"
            )
        )
        self.assertIn("q=lumi+design", request.full_url)
        self.assertIn("count=5", request.full_url)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["x-subscription-token"], "provider-secret")
        self.assertEqual(headers["cache-control"], "no-cache")
        self.assertEqual(timeout, 12.0)
        handler = build_opener.call_args.args[0]
        self.assertIsInstance(handler, _NoRedirectHandler)

    def test_redirect_handler_never_creates_followup_request(self) -> None:
        handler = _NoRedirectHandler()
        redirected = handler.redirect_request(
            object(),
            None,
            302,
            "Found",
            {},
            "https://attacker.example/steal-token",
        )
        self.assertIsNone(redirected)


if __name__ == "__main__":
    unittest.main()
