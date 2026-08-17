from __future__ import annotations

import time

from lumi_visual_critic import (
    DimensionAssessment,
    QualityProfileKey,
    QualitySeverity,
    VisualCriticEngine,
    get_builtin_profile,
)


def main() -> None:
    profile = get_builtin_profile(QualityProfileKey.PRODUCTION_WEB)
    assessments = tuple(
        DimensionAssessment(
            dimension=dimension,
            score=82.0 + (index % 7),
            confidence=0.9,
            threshold=profile.thresholds[dimension],
            severity=QualitySeverity.INFO,
            grader_id="benchmark",
        )
        for index, dimension in enumerate(
            sorted(profile.required_dimensions, key=lambda item: item.value)
        )
    )
    started = time.perf_counter()
    score = 0.0
    confidence = 0.0
    iterations = 50_000
    for _ in range(iterations):
        score = VisualCriticEngine._weighted_score(assessments, profile.weights)
        confidence = VisualCriticEngine._weighted_confidence(
            assessments,
            profile.weights,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert 0 <= score <= 100
    assert 0 <= confidence <= 1
    print(
        "NODE50_QUALITY_SCORING_BENCHMARK_PASS "
        f"iterations={iterations} dimensions={len(assessments)} "
        f"elapsed_ms={elapsed_ms:.3f} score={score:.3f}"
    )


if __name__ == "__main__":
    main()
