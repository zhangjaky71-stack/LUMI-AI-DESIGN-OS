from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .contracts import SkillEvalStatus, SkillEvaluationEvidence, SkillManifest
from .errors import SkillRegistryEvaluationError


class SkillEvaluationGate(Protocol):
    def validate(
        self,
        *,
        manifest: SkillManifest,
        subject_hash: str,
        evidence: SkillEvaluationEvidence,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ThresholdSkillEvaluationGate:
    policy_id: str = "skill-publish-v1"
    minimum_score: str = "0.80"

    def validate(
        self,
        *,
        manifest: SkillManifest,
        subject_hash: str,
        evidence: SkillEvaluationEvidence,
    ) -> None:
        if evidence.policy_id != self.policy_id:
            raise SkillRegistryEvaluationError(
                "SKILL_REGISTRY_EVAL_POLICY_MISMATCH"
            )
        if evidence.subject_hash != subject_hash:
            raise SkillRegistryEvaluationError(
                "SKILL_REGISTRY_EVAL_STALE_SUBJECT"
            )
        if evidence.status is not SkillEvalStatus.PASSED:
            raise SkillRegistryEvaluationError(
                "SKILL_REGISTRY_EVAL_NOT_PASSED"
            )
        if Decimal(evidence.score) < Decimal(self.minimum_score):
            raise SkillRegistryEvaluationError(
                "SKILL_REGISTRY_EVAL_SCORE_BELOW_GATE"
            )
