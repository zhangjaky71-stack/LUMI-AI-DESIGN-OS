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
FIXTURE = ROOT / "reports" / "final-acceptance" / "_manual-evidence-contract"


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_final_manual_evidence_gate", GATE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import final manual evidence gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"manual evidence contract invalid: {message}")


def rc() -> dict[str, str]:
    return {
        "git_sha": "d" * 40,
        "version": "1.0.0-rc.manual",
        "migration_head": "0019_stripe_billing_runtime",
    }


def base_record(scenario_id: str, attachment_ref: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "release_id": "manual-contract-001",
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
        "evidence_refs": [copy.deepcopy(attachment_ref)],
        "notes": "Contract fixture only; not production evidence.",
    }


def make_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Path], dict[str, str]]:
    attachment = FIXTURE / "attachments" / "proof.json"
    write_json(attachment, {"schema_version": 1, "proof": "fixture"})
    attachment_ref = {"path": repo(attachment), "sha256": sha(attachment)}

    records: dict[str, dict[str, Any]] = {}
    uat = base_record("UAT-01", attachment_ref)
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

    billing = base_record("BILLING-UX-01", attachment_ref)
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

    browser1 = base_record("BROWSER-01", attachment_ref)
    browser1["clients"] = [
        {
            "browser": "chrome",
            "browser_version": "stable-fixture",
            "os": "Windows",
            "os_version": "fixture",
            "real_browser": True,
            "status": "PASS",
        },
        {
            "browser": "edge",
            "browser_version": "stable-fixture",
            "os": "Windows",
            "os_version": "fixture",
            "real_browser": True,
            "status": "PASS",
        },
    ]
    records["BROWSER-01"] = browser1

    browser2 = base_record("BROWSER-02", attachment_ref)
    browser2["clients"] = [
        {
            "browser": "safari",
            "browser_version": "stable-fixture",
            "os": "macOS",
            "os_version": "fixture",
            "real_browser": True,
            "engine_preflight_only": False,
            "status": "PASS",
        },
        {
            "browser": "firefox",
            "browser_version": "stable-fixture",
            "os": "Windows",
            "os_version": "fixture",
            "real_browser": True,
            "status": "PASS",
        },
    ]
    records["BROWSER-02"] = browser2

    a11y = base_record("A11Y-01", attachment_ref)
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

    record_paths: dict[str, Path] = {}
    items: list[dict[str, Any]] = []
    for scenario_id, record in records.items():
        path = FIXTURE / "manual" / f"{scenario_id.lower()}.json"
        write_json(path, record)
        record_paths[scenario_id] = path
        items.append(
            {
                "id": scenario_id,
                "status": "PASS",
                "evidence_refs": [{"path": repo(path), "sha256": sha(path)}],
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
        "release_id": "manual-contract-001",
        "release_candidate": rc(),
    }
    evidence = {
        "schema_version": 1,
        "release_id": "manual-contract-001",
        "release_candidate": rc(),
        "items": items,
    }
    return release, evidence, record_paths, attachment_ref


def refresh_item_ref(evidence: dict[str, Any], scenario_id: str, path: Path) -> None:
    item = next(item for item in evidence["items"] if item["id"] == scenario_id)
    item["evidence_refs"] = [{"path": repo(path), "sha256": sha(path)}]


def main() -> int:
    gate = load_gate()
    if FIXTURE.exists():
        shutil.rmtree(FIXTURE)
    try:
        release, evidence, paths, _ = make_fixture()
        clean = gate.evaluate(copy.deepcopy(release), copy.deepcopy(evidence))
        require(clean["passed"] is True, f"clean fixture rejected: {clean['blockers']}")

        safari_path = paths["BROWSER-02"]
        safari_clean = json.loads(safari_path.read_text(encoding="utf-8"))
        safari_bad = copy.deepcopy(safari_clean)
        safari_bad["clients"][0]["real_browser"] = False
        safari_bad["clients"][0]["engine_preflight_only"] = True
        write_json(safari_path, safari_bad)
        safari_evidence = copy.deepcopy(evidence)
        refresh_item_ref(safari_evidence, "BROWSER-02", safari_path)
        result = gate.evaluate(copy.deepcopy(release), safari_evidence)
        require(
            result["passed"] is False
            and any("Safari cannot be satisfied" in blocker for blocker in result["blockers"]),
            "WebKit-only Safari substitution must block",
        )
        write_json(safari_path, safari_clean)

        chrome_path = paths["BROWSER-01"]
        chrome_clean = json.loads(chrome_path.read_text(encoding="utf-8"))
        chrome_bad = copy.deepcopy(chrome_clean)
        chrome_bad["clients"][0]["browser_version"] = "PENDING"
        write_json(chrome_path, chrome_bad)
        chrome_evidence = copy.deepcopy(evidence)
        refresh_item_ref(chrome_evidence, "BROWSER-01", chrome_path)
        require(
            gate.evaluate(copy.deepcopy(release), chrome_evidence)["passed"] is False,
            "missing exact browser version must block",
        )
        write_json(chrome_path, chrome_clean)

        a11y_path = paths["A11Y-01"]
        a11y_clean = json.loads(a11y_path.read_text(encoding="utf-8"))
        a11y_bad = copy.deepcopy(a11y_clean)
        screen_reader = next(
            check for check in a11y_bad["manual_checks"] if check["id"] == "screen-reader"
        )
        screen_reader.pop("assistive_technology_version")
        write_json(a11y_path, a11y_bad)
        a11y_evidence = copy.deepcopy(evidence)
        refresh_item_ref(a11y_evidence, "A11Y-01", a11y_path)
        require(
            gate.evaluate(copy.deepcopy(release), a11y_evidence)["passed"] is False,
            "screen-reader evidence without version must block",
        )
        write_json(a11y_path, a11y_clean)

        uat_path = paths["UAT-01"]
        uat_clean = json.loads(uat_path.read_text(encoding="utf-8"))
        uat_bad = copy.deepcopy(uat_clean)
        uat_bad["checks"] = [
            check for check in uat_bad["checks"] if check["id"] != "error-retry-reconnect"
        ]
        write_json(uat_path, uat_bad)
        uat_evidence = copy.deepcopy(evidence)
        refresh_item_ref(uat_evidence, "UAT-01", uat_path)
        require(
            gate.evaluate(copy.deepcopy(release), uat_evidence)["passed"] is False,
            "UAT missing error/retry/reconnect check must block",
        )
        write_json(uat_path, uat_clean)

        billing_path = paths["BILLING-UX-01"]
        billing_clean = json.loads(billing_path.read_text(encoding="utf-8"))
        billing_bad = copy.deepcopy(billing_clean)
        billing_bad["release_candidate"]["git_sha"] = "e" * 40
        write_json(billing_path, billing_bad)
        billing_evidence = copy.deepcopy(evidence)
        refresh_item_ref(billing_evidence, "BILLING-UX-01", billing_path)
        require(
            gate.evaluate(copy.deepcopy(release), billing_evidence)["passed"] is False,
            "manual evidence RC substitution must block",
        )
        write_json(billing_path, billing_clean)

        responsive = base_record(
            "RESPONSIVE-01",
            {
                "path": repo(FIXTURE / "attachments" / "proof.json"),
                "sha256": sha(FIXTURE / "attachments" / "proof.json"),
            },
        )
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
        write_json(responsive_path, responsive)
        responsive_evidence = copy.deepcopy(evidence)
        responsive_item = next(
            item for item in responsive_evidence["items"] if item["id"] == "RESPONSIVE-01"
        )
        responsive_item["status"] = "PASS"
        responsive_item["evidence_refs"] = [
            {"path": repo(responsive_path), "sha256": sha(responsive_path)}
        ]
        require(
            gate.evaluate(copy.deepcopy(release), responsive_evidence)["passed"] is True,
            "responsive PASS fixture with tested client should pass",
        )

        responsive_bad = copy.deepcopy(responsive)
        responsive_bad["clients"] = []
        write_json(responsive_path, responsive_bad)
        responsive_item["evidence_refs"] = [
            {"path": repo(responsive_path), "sha256": sha(responsive_path)}
        ]
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
                        "missing_browser_version_blocked": True,
                        "missing_screen_reader_version_blocked": True,
                        "missing_uat_retry_check_blocked": True,
                        "manual_rc_substitution_blocked": True,
                        "responsive_defer_allowed": True,
                        "responsive_pass_requires_client": True,
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
