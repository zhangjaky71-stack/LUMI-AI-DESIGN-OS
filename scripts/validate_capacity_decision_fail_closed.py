#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "scripts" / "production-deployment-decision.py"
ROLLBACK = ROOT / "scripts" / "production-rollback-rehearsal-decision.py"
RECOVERY = ROOT / "scripts" / "production-recovery-decision.py"

SERVICE_NAMES = (
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "outbox-dispatcher",
    "sandbox-runtime",
)
EXPECTED_DEPLOYMENT_ID = "prod-capacity-contract-001"
SOURCE = "terraform-live-state"
SCOPE = "production-app-service-desired-counts"


class CapacityDecisionContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CapacityDecisionContractError(message)


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import {path.name}")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def counts() -> dict[str, int]:
    return {name: (2 if name == "outbox-dispatcher" else 3) for name in SERVICE_NAMES}


def services() -> list[dict[str, Any]]:
    expected = counts()
    return [
        {
            "service_name": name,
            "expected_desired_count": expected[name],
            "desired_count": expected[name],
            "capacity_matches": True,
        }
        for name in SERVICE_NAMES
    ]


def runtime() -> dict[str, Any]:
    return {
        "capacity_contract": {
            "schema_version": 1,
            "source": SOURCE,
            "scope": SCOPE,
            "deployment_id": EXPECTED_DEPLOYMENT_ID,
            "service_desired_counts": counts(),
        }
    }


def invoke(
    module: ModuleType,
    runtime_value: dict[str, Any],
    service_rows: list[dict[str, Any]],
) -> tuple[dict[str, int], list[str]]:
    blockers: list[str] = []
    kwargs: dict[str, Any] = {
        "expected_deployment_id": EXPECTED_DEPLOYMENT_ID,
        "blockers": blockers,
    }
    if module is ROLLBACK_MODULE:
        kwargs["label"] = "contract"
    result = module._validate_capacity_contract(runtime_value, service_rows, **kwargs)
    return result, blockers


def must_fail_closed(
    module: ModuleType,
    mutate: Callable[[dict[str, Any], list[dict[str, Any]]], None],
    label: str,
) -> None:
    runtime_value = runtime()
    service_rows = services()
    mutate(runtime_value, service_rows)
    result, blockers = invoke(module, runtime_value, service_rows)
    require(result == {}, f"{label}: invalid capacity evidence leaked a canonical count map")
    require(bool(blockers), f"{label}: invalid capacity evidence did not emit a blocker")


DEPLOYMENT_MODULE = load(DEPLOYMENT, "lumi_capacity_deployment_decision")
ROLLBACK_MODULE = load(ROLLBACK, "lumi_capacity_rollback_decision")
RECOVERY_MODULE = load(RECOVERY, "lumi_capacity_recovery_decision")
MODULES = (DEPLOYMENT_MODULE, ROLLBACK_MODULE, RECOVERY_MODULE)


def main() -> int:
    for module in MODULES:
        clean, blockers = invoke(module, runtime(), services())
        require(clean == counts(), f"{module.__name__}: clean capacity contract did not normalize")
        require(blockers == [], f"{module.__name__}: clean capacity contract emitted blockers")

        must_fail_closed(
            module,
            lambda value, _rows: value["capacity_contract"].__setitem__("schema_version", 2),
            f"{module.__name__} schema",
        )
        must_fail_closed(
            module,
            lambda value, _rows: value["capacity_contract"].__setitem__("source", "manifest"),
            f"{module.__name__} source",
        )
        must_fail_closed(
            module,
            lambda value, _rows: value["capacity_contract"].__setitem__("scope", "other"),
            f"{module.__name__} scope",
        )
        must_fail_closed(
            module,
            lambda value, _rows: value["capacity_contract"].__setitem__("deployment_id", "prod-other"),
            f"{module.__name__} deployment owner",
        )

        def drift_map(value: dict[str, Any], _rows: list[dict[str, Any]]) -> None:
            value["capacity_contract"]["service_desired_counts"]["outbox-dispatcher"] += 1

        must_fail_closed(module, drift_map, f"{module.__name__} row/map mismatch")

    print("capacity decision fail-closed contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CapacityDecisionContractError as exc:
        raise SystemExit(f"capacity decision fail-closed contract failed: {exc}") from exc
