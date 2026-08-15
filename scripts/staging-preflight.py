#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

MAX_RESPONSE_BYTES = 64 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def validate_base_url(raw: str) -> str:
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SystemExit("staging base URL must be HTTPS without embedded credentials")
    if parsed.query or parsed.fragment:
        raise SystemExit("staging base URL must not include query or fragment")
    if os.getenv("LUMI_STAGING_HOST_ACK") != parsed.hostname:
        raise SystemExit("LUMI_STAGING_HOST_ACK must exactly match the staging hostname")
    if os.getenv("LUMI_STAGING_ENV_ACK") != "staging":
        raise SystemExit("LUMI_STAGING_ENV_ACK must equal 'staging'")
    return raw.rstrip("/")


def get_json(opener: urllib.request.OpenerDirector, url: str, timeout: float) -> tuple[dict[str, object], dict[str, str]]:
    request = urllib.request.Request(url, method="GET", headers={"accept": "application/json", "user-agent": "lumi-staging-preflight/1"})
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise SystemExit(f"{url} returned HTTP {response.status}")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise SystemExit(f"{url} response exceeded {MAX_RESPONSE_BYTES} bytes")
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise SystemExit(f"{url} did not return a JSON object")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return payload, headers
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{url} returned HTTP {exc.code}; redirects are not followed") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{url} preflight failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only production-like staging preflight")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    if not 0.5 <= args.timeout <= 30:
        parser.error("timeout must be 0.5..30 seconds")
    base = validate_base_url(args.base_url)
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))

    results: dict[str, object] = {}
    for path in ["/health/live", "/health/ready", "/version"]:
        payload, headers = get_json(opener, base + path, args.timeout)
        if payload.get("service") != "api" or payload.get("status") != "ok":
            raise SystemExit(f"{path} returned unexpected service/status payload")
        if payload.get("version") != args.expected_version:
            raise SystemExit(f"{path} version mismatch: expected {args.expected_version!r}, got {payload.get('version')!r}")
        if path == "/version":
            required_headers = {
                "x-content-type-options": "nosniff",
                "referrer-policy": "no-referrer",
                "cross-origin-resource-policy": "same-origin",
            }
            for header, expected in required_headers.items():
                if headers.get(header) != expected:
                    raise SystemExit(f"security header {header} mismatch on staging API")
            if "content-security-policy" not in headers:
                raise SystemExit("content-security-policy header missing on staging API")
        results[path] = {"status": "PASS", "version": payload.get("version")}

    output = {
        "schema_version": 1,
        "kind": "staging_read_only_preflight",
        "base_host": urllib.parse.urlsplit(base).hostname,
        "expected_version": args.expected_version,
        "checks": results,
        "side_effects": "none",
        "passed": True,
    }
    encoded = json.dumps(output, indent=2, sort_keys=True)
    if args.output == "-":
        print(encoded)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
