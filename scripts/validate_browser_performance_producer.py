#!/usr/bin/env python3
from __future__ import annotations

import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "playwright.performance.config.ts"
SPEC = ROOT / "apps" / "web" / "e2e" / "performance" / "canvas-large-document.release.spec.ts"
HARNESS = ROOT / "apps" / "web" / "e2e" / "performance" / "node69-multipage-harness.ts"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_sources(config: str, spec: str, harness: str) -> None:
    require('LUMI_PERF_BASE_URL' in config, "release browser config must require an external base URL")
    require('url.protocol !== "https:"' in config, "release browser config must require HTTPS")
    for marker in ('host === "localhost"', 'host === "127.0.0.1"', 'host === "::1"'):
        require(marker in config, f"loopback rejection marker missing: {marker}")
    require("webServer" not in config, "release browser config must not start a loopback web server")
    require("workers: 1" in config and "retries: 0" in config, "reference concurrency/retry contract drift")
    require('"--use-angle=swiftshader"' in config, "SwiftShader launch mode missing")
    require('"--disable-features=Vulkan"' in config, "Vulkan drift guard missing")
    require('"--enable-precise-memory-info"' in config, "precise heap telemetry launch mode missing")
    require('viewport: { width: 1440, height: 900 }' in config, "reference viewport drift")
    require('timezoneId: "UTC"' in config, "reference timezone drift")

    for marker in (
        'requireSha("LUMI_PERF_SOURCE_RC_SHA")',
        'requireSha("LUMI_PERF_EVIDENCE_HEAD_SHA")',
        'await route.abort("blockedbyclient")',
        'Emulation.setCPUThrottlingRate',
        'rate: 4',
        'profile.duration_seconds).toBe(600)',
        'simple-500',
        'simple-1000',
        'image-heavy-1000',
        'installNode69MultiPageHarness(page)',
        'readNode69MultiPageShape(page)',
        'page_count: 4',
        'node_count: 1000',
        'browser-canvas-F.json',
        'LCP evidence unavailable',
        'INP/Event Timing evidence unavailable',
        'precise Chromium heap telemetry unavailable',
        'required F metric missing',
    ):
        require(marker in spec, f"browser release producer marker missing: {marker}")

    for metric in (
        '"fps"',
        '"long_tasks"',
        '"heap_memory_mb"',
        '"load_ms"',
        '"zoom_latency_ms"',
        '"pan_latency_ms"',
        '"interaction_latency_ms"',
        '"lcp_ms"',
        '"inp_ms"',
        '"cls"',
    ):
        require(metric in spec, f"required F output metric missing: {metric}")

    require("pageCount = 4" in harness, "multi-page harness must expose four pages")
    require("nodesPerPage = 250" in harness, "multi-page harness must total 1000 nodes")
    require("page_count: pageCount" in harness and "node_count: pageCount * nodesPerPage" in harness, "multi-page shape provenance missing")
    require("requestAnimationFrame(() => requestAnimationFrame" in harness, "multi-page cycle must cross rendered frames")
    require("delete scopedWindow.__LUMI_NODE69_MULTI_PAGE__" in harness, "multi-page harness cleanup contract missing")


def negative_drills(config: str, spec: str, harness: str) -> int:
    drills = [
        ("loopback-allowed", config.replace('host === "localhost"', 'host === "disabled-localhost"', 1), spec, harness),
        ("web-server-added", config + "\n// webServer regression\n", spec, harness),
        ("external-origin-not-blocked", config, spec.replace('await route.abort("blockedbyclient")', 'await route.continue()', 1), harness),
        ("cpu-throttle-drift", config, spec.replace('rate: 4', 'rate: 1', 1), harness),
        ("long-session-shortened", config, spec.replace('profile.duration_seconds).toBe(600)', 'profile.duration_seconds).toBe(60)', 1), harness),
        ("image-scenario-removed", config, spec.replace('"image-heavy-1000"', '"image-heavy-disabled"', 1), harness),
        ("multi-page-reduced", config, spec, harness.replace("pageCount = 4", "pageCount = 1", 1)),
        ("missing-inp", config, spec.replace('"inp_ms"', '"inp_disabled"', 1), harness),
    ]
    blocked = 0
    for name, candidate_config, candidate_spec, candidate_harness in drills:
        try:
            validate_sources(candidate_config, candidate_spec, candidate_harness)
        except AssertionError:
            blocked += 1
        else:
            raise AssertionError(f"negative drill did not block: {name}")
    return blocked


def main() -> int:
    config = CONFIG.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    harness = HARNESS.read_text(encoding="utf-8")
    validate_sources(config, spec, harness)
    blocked = negative_drills(config, spec, harness)
    require(blocked == 8, "all eight browser producer negative drills must block")
    print(f"[browser-performance-producer] PASS: release browser source contract validated; negative_drills={blocked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
