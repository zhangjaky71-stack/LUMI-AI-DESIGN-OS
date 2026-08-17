from __future__ import annotations

import json
from pathlib import Path

from lumi_api.constraint_validator import P0_VALIDATORS, stable_violation_id

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    required = [
        ROOT / "packages/design-constraints/src/validator/runtime.ts",
        ROOT / "packages/design-constraints/src/validator/validators.ts",
        ROOT / "packages/design-constraints/src/validator/solver.ts",
        ROOT / "apps/api/src/lumi_api/constraint_validator/runtime.py",
        ROOT / "apps/api/src/lumi_api/constraint_validator/validators.py",
        ROOT / "apps/api/src/lumi_api/constraint_validator/solver.py",
        ROOT / "packages/design-constraints/fixtures/validator-conformance-v1.json",
        ROOT / "reports/nodes/NODE-39/gap-ledger.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert not missing, f"NODE39_REQUIRED_FILES_MISSING:{missing}"
    assert len(P0_VALIDATORS) == 12

    fixture = json.loads(
        (ROOT / "packages/design-constraints/fixtures/validator-conformance-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert tuple(fixture["p0_validators"]) == P0_VALIDATORS
    assert len(fixture["stable_violation_vectors"]) == 4
    for vector in fixture["stable_violation_vectors"]:
        actual = stable_violation_id(
            constraint_id=vector["constraint_id"],
            validator=vector["validator"],
            affected_node_ids=tuple(vector["affected_node_ids"]),
            message_code=vector["message_code"],
        )
        assert actual == vector["expected"], (actual, vector["expected"])

    ledger = json.loads(
        (ROOT / "reports/nodes/NODE-39/gap-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger["node"] == "NODE-39"
    assert len(ledger["gaps"]) == 5

    forbidden = (
        "openai",
        "anthropic",
        "langchain",
        "langgraph",
        "pixi",
        "react",
    )
    for path in required[:6]:
        source = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert f"import {token}" not in source
            assert f"from {token}" not in source

    print("NODE39_CONSTRAINT_VALIDATOR_VALIDATION_PASS")
    print(f"p0_validators={len(P0_VALIDATORS)}")
    print(f"stable_id_vectors={len(fixture['stable_violation_vectors'])}")
    print(f"gaps={len(ledger['gaps'])}")


if __name__ == "__main__":
    main()
