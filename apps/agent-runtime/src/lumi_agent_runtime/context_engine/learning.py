from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class CorrectionTarget(StrEnum):
    PROJECT_SUMMARY = "PROJECT_SUMMARY"
    BRAND_RULE = "BRAND_RULE"
    STRUCTURED_PREFERENCE = "STRUCTURED_PREFERENCE"


@dataclass(frozen=True, slots=True)
class CorrectionSignal:
    organization_id: UUID
    project_id: UUID
    target: CorrectionTarget
    key: str
    corrected_value: str
    source_ref: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.key or not self.corrected_value or not self.source_ref:
            raise ValueError("CONTEXT_CORRECTION_INVALID")
        if not 0 <= self.confidence <= 1:
            raise ValueError("CONTEXT_CORRECTION_CONFIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class LearningProposal:
    organization_id: UUID
    project_id: UUID
    target: CorrectionTarget
    key: str
    value: str
    source_ref: str
    confidence: float


class ProjectLearningPort(Protocol):
    async def submit_correction(self, proposal: LearningProposal) -> str: ...


class ContextFeedbackLearner:
    """Promotes explicit structured corrections; never stores raw chat history."""

    def __init__(self, writer: ProjectLearningPort) -> None:
        self.writer = writer

    async def learn(self, signal: CorrectionSignal) -> str:
        proposal = LearningProposal(
            organization_id=signal.organization_id,
            project_id=signal.project_id,
            target=signal.target,
            key=signal.key,
            value=signal.corrected_value,
            source_ref=signal.source_ref,
            confidence=signal.confidence,
        )
        return await self.writer.submit_correction(proposal)
