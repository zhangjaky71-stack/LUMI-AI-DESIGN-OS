#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import socket
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_RESPONSE_BYTES = 128 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
    return ordered[index]


def validate_target(raw: str) -> str:
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise SystemExit("target must be an http(s) URL without embedded credentials")
    host = parsed.hostname
    loopback_names = {"localhost", "127.0.0.1", "::1"}
    is_loopback = host in loopback_names
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        resolved = {item[4][0] for item in infos}
        if resolved and all(ip.startswith("127.") or ip == "::1" for ip in resolved):
            is_loopback = True
    except socket.gaierror as exc:
        raise SystemExit(f"target hostname does not resolve: {exc}") from exc
    if not is_loopback:
        if os.getenv("LUMI_PERF_ALLOW_REMOTE_TARGET") != "1":
            raise SystemExit("remote target refused; set LUMI_PERF_ALLOW_REMOTE_TARGET=1 only for an authorized environment")
        if os.getenv("LUMI_PERF_REMOTE_HOST_ACK") != host:
            raise SystemExit("remote target refused; LUMI_PERF_REMOTE_HOST_ACK must exactly match the target hostname")
    return raw


def one_request(opener: urllib.request.OpenerDirector, url: str, method: str, body: bytes | None, timeout: float) -> tuple[bool, float, int]:
    started = time.perf_counter()
    status = 0
    ok = False
    try:
        headers = {"accept": "application/json"}
        if body is not None:
            headers["content-type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with opener.open(req, timeout=timeout) as response:
            status = response.status
            response.read(MAX_RESPONSE_BYTES + 1)
            ok = 200 <= status < 400
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        status = 0
    return ok, (time.perf_counter() - started) * 1000, status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--method", choices=["GET", "POST"], default="GET")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--body", default=None, help="small JSON fixture; never logged")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 512:
        parser.error("concurrency must be 1..512")
    if not 1 <= args.requests <= 1_000_000:
        parser.error("requests must be 1..1,000,000")
    if not 0.1 <= args.timeout <= 60:
        parser.error("timeout must be 0.1..60 seconds")
    url = validate_target(args.url)
    body = None if args.body is None else args.body.encode()
    if body is not None and len(body) > 64 * 1024:
        parser.error("body exceeds 64 KiB")
    opener = urllib.request.build_opener(NoRedirect())
    started_wall = time.time()
    started = time.perf_counter()
    results: list[tuple[bool, float, int]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(one_request, opener, url, args.method, body, args.timeout) for _ in range(args.requests)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    elapsed = max(time.perf_counter() - started, 1e-9)
    latencies = [r[1] for r in results]
    errors = sum(1 for ok, _, _ in results if not ok)
    status_classes: dict[str, int] = {}
    for _, _, status in results:
        key = "network" if status == 0 else f"{status // 100}xx"
        status_classes[key] = status_classes.get(key, 0) + 1
    payload = {
        "schema_version": 1,
        "kind": "http_load_raw",
        "target_host": urllib.parse.urlsplit(url).hostname,
        "method": args.method,
        "concurrency": args.concurrency,
        "requests": len(results),
        "duration_seconds": round(elapsed, 6),
        "started_epoch": started_wall,
        "rps": round(len(results) / elapsed, 3),
        "error_rate": round(errors / max(len(results), 1), 6),
        "p50_ms": round(percentile(latencies, 0.50), 3),
        "p95_ms": round(percentile(latencies, 0.95), 3),
        "p99_ms": round(percentile(latencies, 0.99), 3),
        "mean_ms": round(statistics.fmean(latencies), 3) if latencies else 0.0,
        "status_classes": status_classes,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output == "-":
        print(encoded)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
