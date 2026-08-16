from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "final-manual-evidence-gate.py"
RELEASE_ID = "manual-contract-001"
FIXTURE = ROOT / "reports" / "final-acceptance" / RELEASE_ID


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "lumi_final_manual_evidence_gate",
        GATE_PATH,
    )
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import final manual evidence gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def frozen(path: Path) -> dict[str, str]:
    return {"path": repo_path(path), "sha256": digest(path)}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"manual evidence contract invalid: {message}")


def rc() -> dict[str, str]:
    return {
        "git_sha": "d" * 40,
        "version": "1.0.0-rc.manual",
        "migration_head": "0019_stripe_billing_runtime",
    }


def base_record(
    scenario_id: str,
    attachment: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "scenario_id": scenario_id,
        "status": "PASS",
        "release_candidate": rc(),
        "environment": "production",
        "tester": "node73-contract-tester",
        "started_at_utc": "2026-08-16T05:00:00Z",
        "completed_at_utc": "2026-08-16T05:10:00Z",
        "clients": [],
        "checks": [],
        "manual_checks": [],
        "evidence_refs": [copy.deepcopy(attachment)],
        "notes": "Contract fixture only; not production evidence.",
    }


def build_fixture() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Path],
]:
    proof = FIXTURE / "attachments" / "proof.json"
    write_json(proof, {"schema_version": 1, "kind": "fixture-proof"})
    proof_ref = frozen(proof)

    records: dict[str, dict[str, Any]] = {}

    uat = base_record("UAT-01", proof_ref)
    uat["checks"] = [
        {"id": check_id, "status": "PASS"}
        for check_id in (
            "project",
            "agent",
            "generation",
            "canvas",
            "artifact-version",
            "export",
            "error-retry-reconnect",
        )
    ]
    records["UAT-01"] = uat

    billing = base_record("BILLING-UX-01", proof_ref)
    billing["checks"] = [
        {"id": check_id, "status": "PASS"}
        for check_id in (
            "plan-display",
            "authorization",
            "checkout",
            "success-cancel",
            "portal",
            "cancellation",
            "idempotency",
            "csrf-origin",
            "error-states",
        )
    ]
    records["BILLING-UX-01"] = billing

    browser_01 = base_record("BROWSER-01", proof_ref)
    browser_01["clients"] = [
        {
            "browser": "chrome",
            "browser_version": "fixture-chrome",
            "os": "Windows",
            "os_version": "fixture",
            "real_browser": True,
            "status": "PASS",
        },
        {
            "browser": "edge",
            "browser_version": "fixture-edge",
            "os": "Windows",
            "os_version": "fixture",
            "real_browser": True,
            "status": "PASS",
        },
    ]
    records["BROWSER-01"] = browser_01

    browser_02 = base_record("BROWSER-02", proof_ref)
    browser_02["clients"] = [
        {
            "browser": "safari",
            "browser_version": "fixture-safari",
            "os": "macOS",
            "os_version": "fixture",
            "real_browser": True,
            "engine_preflight_only": False,
            "status": "PASS",
        },
        {
            "browser": "firefox",
            "browser_version": "fixture-firefox",
            "os": "Windows",
            "os_version": "fixture",
            "real_browser": True,
            "status": "PASS",
        },
    ]
    records["BROWSER-02"] = browser_02

    a11y = base_record("A11Y-01", proof_ref)
    a11y["manual_checks"] = [
        {"id": "keyboard", "status": "PASS"},
        {"id": "focus", "status": "PASS"},
        {"id": "semantics", "status": "PASS"},
        {"id": "contrast", "status": "PASS"},
        {
            "id": "screen-reader",
            "status": "PASS",
            "assistive_technology": "VoiceOver",
            "assistive_technology_version": "fixture",
        },
    ]
    records["A11Y-01"] = a11y

    paths: dict[str, Path] = {}
    items: list[dict[str, Any]] = []
    for scenario_id, record in records.items():
        path = FIXTURE / "manual" / f"{scenario_id.lower()}.json"
        write_json(path, record)
        paths[scenario_id] = path
        items.append(
            {
                "id": scenario_id,
                "status": "PASS",
                "evidence_refs": [frozen(path)],
            }
        )

    items.append(
        {
            "id": "RESPONSIVE-01",
            "status": "DEFERRED_NON_CRITICAL",
            "evidence_refs": [],
            "gap": {
                "owner": "product",
                "reason": "desktop-only fixture",
                "impact": "none",
                "target_release": "1.1",
                "workaround": "desktop",
            },
        }
    )

    release = {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "release_candidate": rc(),
    }
    evidence = {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "release_candidate": rc(),
        "items": items,
    }
    return release, evidence, paths


def replace_record(
    evidence: dict[str, Any],
    scenario_id: str,
    path: Path,
    record: dict[str, Any],
) -> dict[str, Any]:
    write_json(path, record)
    mutated = copy.deepcopy(evidence)
    item = next(item for item in mutated["items"] if item["id"] == scenario_id)
    item["evidence_refs"] = [frozen(path)]
    return mutated


def main() -> int:
    gate = load_gate()
    if FIXTURE.exists():
        shutil.rmtree(FIXTURE)
    try:
        release, evidence, paths = build_fixture()
        clean = gate.evaluate(copy.deepcopy(release), copy.deepcopy(evidence))
        require(clean["passed"] is True, f"clean fixture rejected: {clean['blockers']}")

        safari_path = paths["BROWSER-02"]
        safari = json.loads(safari_path.read_text(encoding="utf-8"))
        webkit_only = copy.deepcopy(safari)
        webkit_only["clients"][0]["real_browser"] = False
        webkit_only["clients"][0]["engine_preflight_only"] = True
        result = gate.evaluate(
            copy.deepcopy(release),
            replace_record(evidence, "BROWSER-02", safari_path, webkit_only),
        )
        require(
            result["passed"] is False
            and any("Safari cannot be satisfied" in item for item in result["blockers"]),
            "WebKit-only Safari substitution must block",
        )
        write_json(safari_path, safari)

        duplicate_safari = copy.deepcopy(safari)
        duplicate_safari["clients"].append(copy.deepcopy(duplicate_safari["clients"][0]))
        require(
            gate.evaluate(
                copy.deepcopy(release),
                replace_record(
                    evidence,
                    "BROWSER-02",
                    safari_path,
                    duplicate_safari,
                ),
            )["passed"]
            is False,
            "duplicate browser evidence must block",
        )
        write_json(safari_path, safari)

        chrome_path = paths["BROWSER-01"]
        chrome = json.loads(chrome_path.read_text(encoding="utf-8"))
        missing_version = copy.deepcopy(chrome)
        missing_version["clients"][0]["browser_version"] = "PENDING"
        require(
            gate.evaluate(
                copy.deepcopy(release),
                replace_record(
                    evidence,
                    "BROWSER-01",
                    chrome_path,
                    missing_version,
                ),
            )["passed"]
            is False,
            "missing exact browser version must block",
        )
        write_json(chrome_path, chrome)

        a11y_path = paths["A11Y-01"]
        a11y = json.loads(a11y_path.read_text(encoding="utf-8"))
        missing_at_version = copy.deepcopy(a11y)
        next(
            item
            for item in missing_at_version["manual_checks"]
            if item["id"] == "screen-reader"
        ).pop("assistive_technology_version")
        require(
            gate.evaluate(
                copy.deepcopy(release),
                replace_record(
                    evidence,
                    "A11Y-01",
                    a11y_path,
                    missing_at_version,
                ),
            )["passed"]
            is False,
            "screen-reader evidence without version must block",
        )
        write_json(a11y_path, a11y)

        uat_path = paths["UAT-01"]
        uat = json.loads(uat_path.read_text(encoding="utf-8"))
        missing_retry = copy.deepcopy(uat)
        missing_retry["checks"] = [
            item
            for item in missing_retry["checks"]
            if item["id"] != "error-retry-reconnect"
        ]
        require(
            gate.evaluate(
                copy.deepcopy(release),
                replace_record(evidence, "UAT-01", uat_path, missing_retry),
            )["passed"]
            is False,
            "UAT missing error/retry/reconnect check must block",
        )
        write_json(uat_path, uat)

        billing_path = paths["BILLING-UX-01"]
        billing = json.loads(billing_path.read_text(encoding="utf-8"))
        wrong_rc = copy.deepcopy(billing)
        wrong_rc["release_candidate"]["git_sha"] = "e" * 40
        require(
            gate.evaluate(
                copy.deepcopy(release),
                replace_record(
                    evidence,
                    "BILLING-UX-01",
                    billing_path,
                    wrong_rc,
                ),
            )["passed"]
            is False,
            "manual evidence RC substitution must block",
        )
        write_json(billing_path, billing)

        duplicate_items = copy.deepcopy(evidence)
        duplicate_items["items"].append(copy.deepcopy(duplicate_items["items"][0]))
        require(
            gate.evaluate(copy.deepcopy(release), duplicate_items)["passed"] is False,
            "duplicate acceptance scenario IDs must block",
        )

        bad_release = copy.deepcopy(release)
        bad_release["release_id"] = "../unsafe-release"
        bad_evidence = copy.deepcopy(evidence)
        bad_evidence["release_id"] = "../unsafe-release"
        require(
            gate.evaluate(bad_release, bad_evidence)["passed"] is False,
            "malformed release_id must block",
        )

        responsive = base_record("RESPONSIVE-01", frozen(FIXTURE / "attachments" / "proof.json"))
        responsive["clients"] = [
            {
                "device": "mobile-fixture",
                "browser": "chrome",
                "browser_version": "fixture",
                "os": "Android",
                "os_version": "fixture",
                "real_browser": True,
                "status": "PASS",
            }
        ]
        responsive_path = FIXTURE / "manual" / "responsive-01.json"
        responsive_evidence = copy.deepcopy(evidence)
        responsive_item = next(
            item
            for item in responsive_evidence["items"]
            if item["id"] == "RESPONSIVE-01"
        )
        responsive_item["status"] = "PASS"
        responsive_item.pop("gap", None)
        write_json(responsive_path, responsive)
        responsive_item["evidence_refs"] = [frozen(responsive_path)]
        require(
            gate.evaluate(copy.deepcopy(release), responsive_evidence)["passed"] is True,
            "responsive PASS fixture with real client should pass",
        )

        responsive["clients"] = []
        write_json(responsive_path, responsive)
        responsive_item["evidence_refs"] = [frozen(responsive_path)]
        require(
            gate.evaluate(copy.deepcopy(release), responsive_evidence)["passed"] is False,
            "responsive PASS without tested client must block",
        )

        print(
            json.dumps(
                {
                    "status": "PASS",
                    "clean_decision_id": clean["decision_id"],
                    "drills": {
                        "webkit_safari_substitution_blocked": True,
                        "duplicate_browser_blocked": True,
                        "missing_browser_version_blocked": True,
                        "missing_screen_reader_version_blocked": True,
                        "missing_uat_retry_check_blocked": True,
                        "manual_rc_substitution_blocked": True,
                        "duplicate_scenario_id_blocked": True,
                        "unsafe_release_id_blocked": True,
                        "responsive_defer_allowed": True,
                        "responsive_pass_requires_real_client": True,
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        if FIXTURE.exists():
            shutil.rmtree(FIXTURE)


if __name__ == "__main__":
    raise SystemExit(main())
