#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "perf" / "profiles" / "v1"
BUDGETS = ROOT / "perf" / "budgets" / "v1.json"
SCHEMA = ROOT / "perf" / "schema" / "result-v1-schema.json"
EXPECTED = "ABCDEFG"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def main() -> int:
    manifest = load(PROFILES / "manifest.json")
    require(manifest["version"] == 1, "profile manifest must be version 1")
    require(manifest["default_provider_mode"] == "deterministic_mock", "default provider must be deterministic mock")
    require(manifest["real_provider_ratio_default"] == 0, "real providers must default to zero")
    files = manifest["profiles"]
    require(len(files) == 7, "exactly seven A-G profiles are required")

    seen = []
    for filename in files:
        p = load(PROFILES / filename)
        seen.append(p["id"])
        require(p["version"] == 1, f"{filename}: version must be 1")
        require(1 <= p["duration_seconds"] <= 3600, f"{filename}: invalid duration")
        c = p["concurrency"]
        for key in ("connected_users", "http_workers", "ai_generations", "media_jobs", "sse_connections"):
            require(isinstance(c[key], int) and 0 <= c[key] <= 512, f"{filename}: unsafe {key}")
        mix = p["provider_mix"]
        require(mix["real_ratio"] == 0.0, f"{filename}: canonical profile must not call paid providers")
        require(mix["mock_ratio"] == 1.0, f"{filename}: canonical profile must be fully mocked")
        require(p["measure"], f"{filename}: measurement set required")

    require("".join(sorted(seen)) == EXPECTED, "profile IDs must be exactly A-G")
    g = load(PROFILES / "G-mixed-launch.json")["concurrency"]
    require(g["connected_users"] == 100, "launch profile must include 100 connected users")
    require(g["ai_generations"] == 20, "launch profile must include 20 AI generations")
    require(g["media_jobs"] == 10, "launch profile must include 10 media jobs")
    require(g["sse_connections"] >= 100, "launch profile must include >=100 SSE connections")

    budgets = load(BUDGETS)
    require(budgets["kind"] == "target" and budgets["measured"] is False, "budgets must be targets, not measurements")
    require(budgets["latency_ms"]["api_cached_metadata_p95_max"] == 300, "cached API target drift")
    require(budgets["latency_ms"]["api_ordinary_p95_max"] == 800, "ordinary API target drift")
    require(budgets["latency_ms"]["enqueue_p95_max"] == 500, "enqueue target drift")
    require(budgets["latency_ms"]["sse_platform_propagation_p95_max"] == 1000, "SSE target drift")

    schema = load(SCHEMA)
    required = set(schema["required"])
    for key in ("http", "resources", "database", "queue", "ai_latency"):
        require(key in required, f"result schema missing {key}")
    ai_required = set(schema["properties"]["ai_latency"]["required"])
    require("provider_ms" in ai_required and "platform_overhead_ms" in ai_required, "provider/platform latency must be separated")
    print("[performance-contract] PASS: A-G profiles, target budgets and result evidence schema verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
