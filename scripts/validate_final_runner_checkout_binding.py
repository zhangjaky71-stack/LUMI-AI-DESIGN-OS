from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run-final-acceptance.py"
MATRIX = ROOT / "final" / "acceptance" / "manifest-v1.json"
FIXTURE = ROOT / "reports" / "final-acceptance" / "_runner-checkout-binding"
RELEASE = FIXTURE / "release-manifest.json"


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_final_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import canonical final runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def candidate(git_sha: str) -> dict[str, str]:
    return {
        "git_sha": git_sha,
        "version": "runner-binding-fixture",
        "migration_head": "runner-binding-fixture",
    }


def write_release(git_sha: str, required: list[str]) -> None:
    specs: dict[str, dict[str, str]] = {}
    for name in required:
        path = FIXTURE / "upstream" / f"{name}.json"
        write_json(
            path,
            {
                "schema_version": 1,
                "decision_id": f"{name}-fixture",
                "passed": True,
                "release_candidate": candidate(git_sha),
            },
        )
        specs[name] = {"path": path.relative_to(ROOT).as_posix()}

    write_json(
        RELEASE,
        {
            "schema_version": 1,
            "release_id": "runner-checkout-binding-fixture",
            "release_candidate": candidate(git_sha),
            "upstream_gates": specs,
        },
    )


def main() -> None:
    runner = load_runner()
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    required = matrix.get("required_upstream_gates")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise SystemExit("fixture could not resolve required upstream gates")
    required_names = [str(item) for item in required]

    if FIXTURE.exists():
        shutil.rmtree(FIXTURE)
    try:
        actual = runner.current_git_sha()
        release_arg = RELEASE.relative_to(ROOT).as_posix()
        matrix_arg = MATRIX.relative_to(ROOT).as_posix()

        write_release(actual, required_names)
        bound = runner.require_current_checkout_binding(release_arg)
        if bound != actual:
            raise SystemExit("final runner did not bind matching current checkout")
        upstream_bound = runner.require_all_upstream_rc_binding(release_arg, matrix_arg)
        if set(upstream_bound) != set(required_names):
            raise SystemExit("not every required upstream gate was RC-bound")

        stale = ("0" if actual[0] != "0" else "1") + actual[1:]
        write_release(stale, required_names)
        try:
            runner.require_current_checkout_binding(release_arg)
        except SystemExit as exc:
            if "FINAL_ACCEPTANCE_CHECKOUT_SHA_MISMATCH" not in str(exc):
                raise SystemExit(f"unexpected stale-RC failure contract: {exc}") from exc
        else:
            raise SystemExit("stale release candidate was accepted on a different checkout")

        write_release(actual, required_names)
        security = FIXTURE / "upstream" / "security.json"
        security_payload = json.loads(security.read_text(encoding="utf-8"))
        security_payload["release_candidate"] = candidate(stale)
        write_json(security, security_payload)
        try:
            runner.require_all_upstream_rc_binding(release_arg, matrix_arg)
        except SystemExit as exc:
            if "FINAL_ACCEPTANCE_UPSTREAM_RC_MISMATCH" not in str(exc):
                raise SystemExit(f"unexpected upstream-RC failure contract: {exc}") from exc
            if "security" not in str(exc):
                raise SystemExit("upstream mismatch did not identify the stale security gate")
        else:
            raise SystemExit("stale Security decision was accepted for a different RC")
    finally:
        if FIXTURE.exists():
            shutil.rmtree(FIXTURE)

    print("FINAL_RUNNER_CHECKOUT_AND_UPSTREAM_BINDING_CONTRACT_PASS")


if __name__ == "__main__":
    main()
