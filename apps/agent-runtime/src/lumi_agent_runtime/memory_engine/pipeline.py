from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid5

from .contracts import (
    MemoryAccessContext,
    MemoryCandidate,
    MemoryCandidateOutcome,
    MemoryDecision,
    MemoryRecord,
    MemoryStatus,
)
from .policy import evaluate_write_policy
from .repository import MemoryRepository
from .sensitivity import classify_candidate


class MemoryCandidatePipeline:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    async def process(
        self,
        candidate: MemoryCandidate,
        *,
        access: MemoryAccessContext,
        now: datetime | None = None,
    ) -> MemoryDecision:
        observed_at = now or datetime.now(UTC)
        sensitivity = classify_candidate(candidate)
        if sensitivity.classification.value != "NONE":
            # Deliberately do not persist rejected sensitive content in the candidate table.
            return MemoryDecision(
                MemoryCandidateOutcome.REJECT_SENSITIVE,
                candidate.candidate_id,
                reason=sensitivity.reason,
            )

        policy = evaluate_write_policy(candidate, access)
        if not policy.allowed:
            # Cross-tenant/scope-spoofed content is not persisted as a candidate either.
            return MemoryDecision(policy.outcome, candidate.candidate_id, reason=policy.reason)
        if policy.outcome == MemoryCandidateOutcome.BRAND_RULE_PROPOSAL:
            await self.repository.insert_candidate(
                candidate,
                outcome=policy.outcome.value,
                reason=policy.reason,
            )
            return MemoryDecision(policy.outcome, candidate.candidate_id, reason=policy.reason)

        existing = await self.repository.find_active_by_key(
            organization_id=candidate.organization_id,
            scope_type=candidate.scope_type.value,
            scope_id=candidate.scope_id,
            kind=candidate.kind.value,
            semantic_key=candidate.semantic_key,
        )
        exact = next((item for item in existing if item.content_hash == candidate.content_hash), None)
        confidence = max(candidate.confidence, 0.9 if candidate.explicit_remember else candidate.confidence)
        if exact is not None:
            confirmed = replace(
                exact,
                confidence=max(exact.confidence, confidence),
                last_confirmed_at=observed_at,
                source_refs=_merge_source_refs(exact.source_refs, candidate.source_refs),
                embedding=candidate.embedding or exact.embedding,
                embedding_model=candidate.embedding_model or exact.embedding_model,
                embedding_version=candidate.embedding_version or exact.embedding_version,
                version=exact.version + 1,
            )
            confirmed = await self.repository.update_record(confirmed, expected_version=exact.version)
            await self.repository.insert_candidate(
                candidate,
                outcome=MemoryCandidateOutcome.DEDUPLICATE_CONFIRM.value,
                reason="MEMORY_EXACT_DUPLICATE_CONFIRMED",
            )
            return MemoryDecision(
                MemoryCandidateOutcome.DEDUPLICATE_CONFIRM,
                candidate.candidate_id,
                record=confirmed,
                existing_record_id=exact.memory_id,
                reason="MEMORY_EXACT_DUPLICATE_CONFIRMED",
            )

        if existing and not candidate.temporal_coexistence and not (
            candidate.explicit_remember and confidence >= 0.9
        ):
            await self.repository.insert_candidate(
                candidate,
                outcome=MemoryCandidateOutcome.REQUIRE_CONFIRMATION.value,
                reason="MEMORY_CONFLICT_CONFIRMATION_REQUIRED",
            )
            return MemoryDecision(
                MemoryCandidateOutcome.REQUIRE_CONFIRMATION,
                candidate.candidate_id,
                existing_record_id=existing[0].memory_id,
                reason="MEMORY_CONFLICT_CONFIRMATION_REQUIRED",
            )

        supersedes = existing[0] if existing and not candidate.temporal_coexistence else None
        if supersedes is not None:
            superseded = replace(
                supersedes,
                status=MemoryStatus.SUPERSEDED,
                valid_to=observed_at,
                version=supersedes.version + 1,
            )
            await self.repository.update_record(superseded, expected_version=supersedes.version)

        record = MemoryRecord(
            memory_id=uuid5(candidate.candidate_id, "lumi-memory-record"),
            organization_id=candidate.organization_id,
            scope_type=candidate.scope_type,
            scope_id=candidate.scope_id,
            kind=candidate.kind,
            semantic_key=candidate.semantic_key,
            content_structured=candidate.content_structured,
            summary=candidate.summary,
            source_refs=candidate.source_refs,
            confidence=confidence,
            status=MemoryStatus.ACTIVE,
            created_by_type=candidate.created_by_type,
            created_by_id=candidate.created_by_id,
            created_at=observed_at,
            last_confirmed_at=observed_at if candidate.explicit_remember else None,
            expires_at=candidate.expires_at,
            valid_from=observed_at,
            supersedes_id=supersedes.memory_id if supersedes else None,
            embedding=candidate.embedding,
            embedding_model=candidate.embedding_model,
            embedding_version=candidate.embedding_version,
            metadata={**candidate.metadata, "explicit_remember": candidate.explicit_remember},
        )
        record = await self.repository.insert_record(record)
        await self.repository.insert_candidate(
            candidate,
            outcome=MemoryCandidateOutcome.WRITE.value,
            reason="MEMORY_RECORD_WRITTEN",
        )
        return MemoryDecision(
            MemoryCandidateOutcome.WRITE,
            candidate.candidate_id,
            record=record,
            existing_record_id=supersedes.memory_id if supersedes else None,
            reason="MEMORY_RECORD_WRITTEN",
        )


def _merge_source_refs(left, right):
    seen: set[tuple[str, str, str, str]] = set()
    merged = []
    for ref in (*left, *right):
        key = (ref.source_type, ref.source_id, ref.version, ref.content_hash)
        if key not in seen:
            seen.add(key)
            merged.append(ref)
    return tuple(merged)
