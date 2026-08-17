from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import IdentityValidationResult


@dataclass(frozen=True, slots=True)
class IdentityEvidenceScoreAdapter:
    """NODE-39 IdentityScore callable backed by exact NODE-44 validation evidence."""

    by_node_id: Mapping[str, IdentityValidationResult]

    def __call__(self, node: Mapping[str, Any]) -> float | None:
        node_id = node.get("id") or node.get("node_id")
        if node_id is None:
            return None
        result = self.by_node_id.get(str(node_id))
        if result is None or result.score_01 is None:
            return None
        score_failure = "IDENTITY_SCORE_BELOW_THRESHOLD" in result.failure_codes
        if result.failure_codes and not score_failure:
            return None
        return result.score_01


def node39_identity_score_adapter(
    results: Mapping[str, IdentityValidationResult],
) -> IdentityEvidenceScoreAdapter:
    return IdentityEvidenceScoreAdapter(by_node_id=results)
