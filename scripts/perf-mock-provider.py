#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "LumiPerfMock/1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Never log request bodies/prompts. Path/status are enough for a local perf fixture.
        print("[perf-mock] " + (fmt % args))

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "provider": "deterministic_mock"})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/v1/generate":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            self._json(400, {"error": "invalid_content_length"})
            return
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"error": "body_size_rejected"})
            return
        body = self.rfile.read(length)
        digest = hashlib.sha256(body).hexdigest()
        bucket = int(digest[:8], 16)
        latency_ms = 25 + bucket % 76  # deterministic 25..100 ms
        error = bucket % 100 == 0     # deterministic ~1% error fixture
        time.sleep(latency_ms / 1000)
        if error:
            self._json(503, {"status": "mock_transient", "provider_latency_ms": latency_ms, "request_fingerprint": digest[:16]})
            return
        self._json(200, {"status": "succeeded", "provider_latency_ms": latency_ms, "request_fingerprint": digest[:16], "artifact_ref": f"mock://{digest[:24]}"})

    def _json(self, status: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[perf-mock] listening on 127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
