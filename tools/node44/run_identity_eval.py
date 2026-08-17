from __future__ import annotations

import json
from pathlib import Path

from lumi_api.identity_engine.contracts import IdentityType, SignalScore
from lumi_api.identity_engine.scoring import combine_signals


def main() -> None:
    fixture = json.loads(Path("evals/node44/identity-benchmark.json").read_text(encoding="utf-8"))
    cases = fixture["cases"]
    correct = 0
    for case in cases:
        signals = tuple(SignalScore.model_validate(value) for value in case["signals"])
        score, confidence, count, _ = combine_signals(
            IdentityType(case["identity_type"]),
            signals,
            region_quality=case["region_quality"],
            region_confidence=case["region_confidence"],
        )
        passed = bool(
            score is not None
            and count >= case["min_signal_count"]
            and score >= case["threshold"]
            and confidence >= case["min_confidence"]
        )
        if passed != case["expected_pass"]:
            raise AssertionError(
                f"{case['case']}: expected={case['expected_pass']} "
                f"score={score} confidence={confidence}"
            )
        correct += 1
    print(
        f"NODE44_IDENTITY_EVAL_PASS cases={correct} "
        f"accuracy={correct / len(cases):.3f}"
    )


if __name__ == "__main__":
    main()
