from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run-final-acceptance.py"
FIXTURE = ROOT / "reports" / "final-acceptance" / "_runner-checkout-binding"
RELEASE = FIXTURE / "release-manifest.json"


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_final_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import canonical final runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_release(git_sha: str) -> None:
    FIXTURE.mkdir(parents=True, exist_ok=True)
    RELEASE.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release_id": "runner-checkout-binding-fixture",
                "release_candidate": {
                    "git_sha": git_sha,
                    "version": "fixture",
                    "migration_head": "fixture",
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    runner = load_runner()
    if FIXTURE.exists():
        shutil.rmtree(FIXTURE)
    try:
        actual = runner.current_git_sha()
        write_release(actual)
        bound = runner.require_current_checkout_binding(
            RELEASE.relative_to(ROOT).as_posix()
        )
        if bound != actual:
            raise SystemExit("final runner did not bind matching current checkout")

        stale = ("0" if actual[0] != "0" else "1") + actual[1:]
        write_release(stale)
        try:
            runner.require_current_checkout_binding(RELEASE.relative_to(ROOT).as_posix())
        except SystemExit as exc:
            if "FINAL_ACCEPTANCE_CHECKOUT_SHA_MISMATCH" not in str(exc):
                raise SystemExit(
                    f"unexpected stale-RC failure contract: {exc}"
                ) from exc
        else:
            raise SystemExit("stale release candidate was accepted on a different checkout")
    finally:
        if FIXTURE.exists():
            shutil.rmtree(FIXTURE)

    print("FINAL_RUNNER_CHECKOUT_BINDING_CONTRACT_PASS")


if __name__ == "__main__":
    main()
