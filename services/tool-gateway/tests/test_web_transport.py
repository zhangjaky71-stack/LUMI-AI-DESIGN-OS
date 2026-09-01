from __future__ import annotations

import asyncio
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lumi_tool_gateway.web_transport import PinnedStdlibHTTPTransport


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: list[dict[str, str]] = []

    def do_GET(self) -> None:
        self.__class__.requests.append(
            {
                "path": self.path,
                "host": self.headers.get("Host", ""),
                "authorization": self.headers.get("Authorization", ""),
                "cookie": self.headers.get("Cookie", ""),
                "user_agent": self.headers.get("User-Agent", ""),
            }
        )
        body = b"pinned-ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        del format, args


class PinnedStdlibHTTPTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        _Handler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    async def asyncTearDown(self) -> None:
        await asyncio.to_thread(self.server.shutdown)
        await asyncio.to_thread(self.server.server_close)
        self.thread.join(timeout=2)

    async def test_connects_to_pinned_ip_without_dns_and_preserves_host(self) -> None:
        port = self.server.server_port
        transport = PinnedStdlibHTTPTransport()
        response = await transport.fetch(
            url=f"http://does-not-resolve.invalid:{port}/hello?q=1",
            resolved_ip="127.0.0.1",
            host_header="does-not-resolve.invalid",
            timeout_seconds=2.0,
            max_bytes=4096,
            headers={
                "User-Agent": "LUMI-ToolGateway/1.0",
                "Authorization": "must-not-forward",
                "Cookie": "must-not-forward",
                "Host": "attacker.invalid",
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"pinned-ok")
        self.assertEqual(len(_Handler.requests), 1)
        observed = _Handler.requests[0]
        self.assertEqual(observed["path"], "/hello?q=1")
        self.assertEqual(
            observed["host"],
            f"does-not-resolve.invalid:{port}",
        )
        self.assertEqual(observed["authorization"], "")
        self.assertEqual(observed["cookie"], "")
        self.assertEqual(observed["user_agent"], "LUMI-ToolGateway/1.0")

    async def test_rejects_hostname_mismatch_before_network(self) -> None:
        transport = PinnedStdlibHTTPTransport()
        with self.assertRaisesRegex(ValueError, "TOOL_PINNED_TRANSPORT_TARGET_INVALID"):
            await transport.fetch(
                url="http://example.com/",
                resolved_ip="127.0.0.1",
                host_header="other.example",
                timeout_seconds=1.0,
                max_bytes=4096,
                headers={},
            )
        self.assertEqual(_Handler.requests, [])

    async def test_rejects_header_injection_before_network(self) -> None:
        transport = PinnedStdlibHTTPTransport()
        with self.assertRaisesRegex(ValueError, "TOOL_PINNED_TRANSPORT_HEADER_INVALID"):
            await transport.fetch(
                url="http://example.com/",
                resolved_ip="127.0.0.1",
                host_header="example.com",
                timeout_seconds=1.0,
                max_bytes=4096,
                headers={"X-Test": "ok\r\nInjected: yes"},
            )
        self.assertEqual(_Handler.requests, [])


if __name__ == "__main__":
    unittest.main()
