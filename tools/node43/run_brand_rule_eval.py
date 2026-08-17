from __future__ import annotations

import json
from pathlib import Path

from lumi_api.brand_rules.compliance import evaluate_observation
from lumi_api.brand_rules.contracts import (
    BrandObservation,
    BrandRule,
    RuleKind,
    RuleSeverity,
    RuleSource,
)
from lumi_api.domain.ids import new_uuid7

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "evals/node43/brand-rule-fixtures.json"


def main() -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    assert payload["schema"] == "lumi.node43-brand-eval/1.0"
    cases = payload["cases"]
    assert len(cases) >= 20
    for case in cases:
        rule = BrandRule(
            id=new_uuid7(),
            key=case["name"],
            kind=RuleKind(case["kind"]),
            severity=RuleSeverity.HARD,
            source=RuleSource.MANUAL_ADMIN,
            parameters=case["parameters"],
        )
        observation = BrandObservation.model_validate(case["observation"])
        issue = evaluate_observation(rule, observation)
        actual = issue.code if issue is not None else None
        if actual != case["expected"]:
            raise AssertionError(
                f"{case['name']}: expected {case['expected']!r}, got {actual!r}"
            )
    print(f"NODE43_BRAND_RULE_EVAL_PASS cases={len(cases)}")


if __name__ == "__main__":
    main()
