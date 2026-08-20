#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "perf" / "reference-devices" / "v1" / "node69-playwright-chromium-swiftshader.json"
PROFILE = ROOT / "perf" / "profiles" / "v1" / "F-canvas-large-document.json"
PACKAGE = ROOT / "package.json"
REFERENCE_ID = "node69-playwright-chromium-swiftshader-v1"
EXPECTED_MEASURES = {
    "fps",
    "long_tasks",
    "heap_memory_mb",
    "load_ms",
    "zoom_latency_ms",
    "pan_latency_ms",
    "interaction_latency_ms",
    "lcp_ms",
    "inp_ms",
    "cls",
}
EXPECTED_EVIDENCE = {
    "source_rc_sha",
    "evidence_head_sha",
    "base_url",
    "playwright_version",
    "browser_version",
    "user_agent",
    "os",
    "architecture",
    "cpu_model",
    "logical_cpu_count",
    "memory_total_bytes",
    "webgl_vendor",
    "webgl_renderer",
    "viewport",
    "device_scale_factor",
    "cpu_throttle_rate",
    "started_at",
    "finished_at",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def validate(reference: dict, profile: dict, package: dict) -> None:
    require(reference.get("schema_version") == 1, "reference schema_version must be 1")
    require(reference.get("id") == REFERENCE_ID, "reference id drift")
    automation = reference.get("automation", {})
    require(automation.get("framework") == "@playwright/test", "Playwright is the canonical browser harness")
    require(automation.get("version") == package.get("devDependencies", {}).get("@playwright/test"), "reference Playwright version must equal the workspace lock intent")
    require(automation.get("browser") == "chromium", "reference browser must be Chromium")
    require(automation.get("headless") is True, "reference browser must be headless")
    require(automation.get("workers") == 1, "reference benchmark must use exactly one worker")
    require(automation.get("retries") == 0, "reference benchmark must not hide regressions behind retries")

    runtime = reference.get("browser_runtime", {})
    args = set(runtime.get("launch_args", []))
    require("--use-angle=swiftshader" in args, "reference must force the SwiftShader software path")
    require("--disable-features=Vulkan" in args, "reference must disable Vulkan drift")
    require(runtime.get("viewport") == {"width": 1440, "height": 900}, "reference viewport drift")
    require(runtime.get("device_scale_factor") == 1, "reference device scale factor drift")
    require(runtime.get("timezone_id") == "UTC", "reference timezone must be UTC")

    cpu = reference.get("cpu", {})
    require(cpu.get("devtools_emulation") == "Emulation.setCPUThrottlingRate", "CPU throttling contract drift")
    require(cpu.get("rate") == 4, "CPU throttle rate must be 4x")

    runner = reference.get("runner", {})
    require(runner.get("os") == "ubuntu-24.04", "reference runner OS drift")
    require(runner.get("architecture") == "x64", "reference runner architecture drift")
    require(runner.get("physical_hardware_is_identity") is False, "physical GitHub runner hardware must not become canonical identity")
    require(runner.get("capture_runtime_hardware_metadata") is True, "runtime hardware provenance is required")

    network = reference.get("network", {})
    require(network.get("release_target") == "production_like_staging", "release benchmark must target Production-like Staging")
    require(network.get("external_cdn_allowed_during_measurement") is False, "external CDN is forbidden during release measurement")
    require(network.get("loopback_results_are_release_evidence") is False, "loopback smoke cannot become release evidence")
    require(set(reference.get("evidence_required", [])) == EXPECTED_EVIDENCE, "reference evidence inventory drift")

    require(profile.get("id") == "F" and profile.get("category") == "browser_canvas", "F browser-canvas profile identity drift")
    require(profile.get("duration_seconds") == 600, "F long-session duration must remain 600 seconds")
    profile_ref = profile.get("input", {}).get("reference_device")
    require(profile_ref == REFERENCE_ID, "F profile must bind the frozen reference id")
    require("TBD" not in json.dumps(profile, sort_keys=True), "F profile contains unresolved TBD")
    require(set(profile.get("measure", [])) == EXPECTED_MEASURES, "F measurement inventory drift")
    scenarios = profile.get("input", {}).get("scenarios", [])
    require({"nodes": 500, "image_heavy": False} in scenarios, "F must cover 500-node document")
    require({"nodes": 1000, "image_heavy": False} in scenarios, "F must cover 1000-node document")
    require({"nodes": 1000, "image_heavy": True} in scenarios, "F must cover 1000-node image-heavy document")
    require({"multi_page": True, "long_session": True} in scenarios, "F must cover multi-page long-session behavior")


def negative_drills(reference: dict, profile: dict, package: dict) -> int:
    mutations: list[tuple[str, dict, dict, dict]] = []

    changed = copy.deepcopy(profile)
    changed["input"]["reference_device"] = "NODE-69 release device TBD"
    mutations.append(("unresolved-reference", reference, changed, package))

    changed_ref = copy.deepcopy(reference)
    changed_ref["automation"]["version"] = "0.0.0"
    mutations.append(("playwright-version-drift", changed_ref, profile, package))

    changed_ref = copy.deepcopy(reference)
    changed_ref["network"]["external_cdn_allowed_during_measurement"] = True
    mutations.append(("external-cdn-enabled", changed_ref, profile, package))

    changed_ref = copy.deepcopy(reference)
    changed_ref["network"]["loopback_results_are_release_evidence"] = True
    mutations.append(("loopback-promoted", changed_ref, profile, package))

    changed_ref = copy.deepcopy(reference)
    changed_ref["cpu"]["rate"] = 1
    mutations.append(("cpu-throttle-drift", changed_ref, profile, package))

    changed_ref = copy.deepcopy(reference)
    changed_ref["evidence_required"].remove("webgl_renderer")
    mutations.append(("missing-runtime-provenance", changed_ref, profile, package))

    changed = copy.deepcopy(profile)
    changed["measure"].remove("inp_ms")
    mutations.append(("missing-browser-measure", reference, changed, package))

    blocked = 0
    for name, mutated_reference, mutated_profile, mutated_package in mutations:
        try:
            validate(mutated_reference, mutated_profile, mutated_package)
        except AssertionError:
            blocked += 1
        else:
            raise AssertionError(f"negative drill did not block: {name}")
    return blocked


def main() -> int:
    reference = load(REFERENCE)
    profile = load(PROFILE)
    package = load(PACKAGE)
    validate(reference, profile, package)
    blocked = negative_drills(reference, profile, package)
    require(blocked == 7, "all seven canvas reference negative drills must block")
    print(f"[canvas-performance-reference] PASS: frozen F reference validated; negative_drills={blocked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
