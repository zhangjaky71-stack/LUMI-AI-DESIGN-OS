#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def get(url: str) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "lumi-production-smoke/1"}, method="GET")
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    response = opener.open(request, timeout=15)
    return response.status, {key.lower(): value for key, value in response.headers.items()}, response.read(1_048_576)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or parsed.hostname != args.expected_host or parsed.username or parsed.password:
        raise SystemExit("production smoke requires exact HTTPS host and no embedded credentials")

    results: dict[str, object] = {}
    for path in ["/health/live", "/health/ready", "/version"]:
        try:
            status, headers, body = get(base + path)
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as exc:
            raise SystemExit(f"production smoke request failed for {path}: {exc}") from exc
        if status != 200:
            raise SystemExit(f"production smoke {path} returned {status}")
        results[path] = {"status": status}
        if path == "/version":
            payload = json.loads(body.decode("utf-8"))
            if payload.get("version") != args.expected_version:
                raise SystemExit("production /version does not match release manifest")
            results[path] = {"status": status, "version": payload.get("version")}
        if path == "/health/ready":
            required = {
                "strict-transport-security",
                "x-content-type-options",
                "content-security-policy",
            }
            missing = sorted(required - set(headers))
            if missing:
                raise SystemExit(f"production security headers missing: {missing}")
            results[path] = {"status": status, "security_headers": sorted(required)}

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema_version": 1, "passed": True, "base_url": base, "results": results}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("production read-only smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
