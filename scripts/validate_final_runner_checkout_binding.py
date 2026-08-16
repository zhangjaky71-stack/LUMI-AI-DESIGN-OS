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


def candidate(identity: tuple[str, str, str]) -> dict[str, str]:
    return {
        "git_sha": identity[0],
        "version": identity[1],
        "migration_head": identity[2],
    }


def write_release(identity: tuple[str, str, str], required: list[str]) -> None:
    specs: dict[str, dict[str, str]] = {}
    for name in required:
        path = FIXTURE / "upstream" / f"{name}.json"
        write_json(
            path,
            {
                "schema_version": 1,
                "decision_id": f"{name}-fixture",
                "passed": True,
                "release_candidate": candidate(identity),
            },
        )
        specs[name] = {"path": path.relative_to(ROOT).as_posix()}

    write_json(
        RELEASE,
        {
            "schema_version": 1,
            "release_id": "runner-checkout-binding-fixture",
            "release_candidate": candidate(identity),
            "upstream_gates": specs,
        },
    )


def expect_failure(callable_obj, marker: str, *, label: str) -> None:
    try:
        callable_obj()
    except SystemExit as exc:
        if marker not in str(exc):
            raise SystemExit(f"unexpected {label} failure contract: {exc}") from exc
    else:
        raise SystemExit(f"{label} unexpectedly passed")


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
        actual = runner.repository_release_identity()
        release_arg = RELEASE.relative_to(ROOT).as_posix()
        matrix_arg = MATRIX.relative_to(ROOT).as_posix()

        write_release(actual, required_names)
        if runner.require_repository_identity_binding(release_arg) != actual:
            raise SystemExit("final runner did not bind repository release identity")
        upstream_bound = runner.require_all_upstream_rc_binding(release_arg, matrix_arg)
        if set(upstream_bound) != set(required_names):
            raise SystemExit("not every required upstream gate was RC-bound")

        stale_sha = ("0" if actual[0][0] != "0" else "1") + actual[0][1:]
        write_release((stale_sha, actual[1], actual[2]), required_names)
        expect_failure(
            lambda: runner.require_repository_identity_binding(release_arg),
            "FINAL_ACCEPTANCE_REPOSITORY_IDENTITY_MISMATCH",
            label="stale checkout SHA",
        )

        write_release((actual[0], actual[1] + "-wrong", actual[2]), required_names)
        expect_failure(
            lambda: runner.require_repository_identity_binding(release_arg),
            "FINAL_ACCEPTANCE_REPOSITORY_IDENTITY_MISMATCH",
            label="wrong VERSION binding",
        )

        write_release((actual[0], actual[1], actual[2] + "-wrong"), required_names)
        expect_failure(
            lambda: runner.require_repository_identity_binding(release_arg),
            "FINAL_ACCEPTANCE_REPOSITORY_IDENTITY_MISMATCH",
            label="wrong Alembic head binding",
        )

        write_release(actual, required_names)
        security = FIXTURE / "upstream" / "security.json"
        security_payload = json.loads(security.read_text(encoding="utf-8"))
        security_payload["release_candidate"] = candidate((stale_sha, actual[1], actual[2]))
        write_json(security, security_payload)
        expect_failure(
            lambda: runner.require_all_upstream_rc_binding(release_arg, matrix_arg),
            "FINAL_ACCEPTANCE_UPSTREAM_RC_MISMATCH",
            label="stale Security decision",
        )
    finally:
        if FIXTURE.exists():
            shutil.rmtree(FIXTURE)

    print("FINAL_RUNNER_REPOSITORY_AND_UPSTREAM_BINDING_CONTRACT_PASS")


if __name__ == "__main__":
    main()
