from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from langgraph.store.base import BaseStore

from lumi_agent_runtime.context_engine import ContextLayer, ContextRequest, LayerBudget
from lumi_agent_runtime.memory_engine import (
    DeepAgentMemoryStore,
    InMemoryMemoryRepository,
    MemoryAccessContext,
    MemoryActorType,
    MemoryCandidate,
    MemoryCandidateOutcome,
    MemoryContextSource,
    MemoryEngineService,
    MemoryKind,
    MemoryRetriever,
    MemoryScope,
    MemorySearchQuery,
    MemorySourceRef,
    MemoryStatus,
)

ORG = UUID("01920000-0000-7000-8000-000000000001")
OTHER_ORG = UUID("01920000-0000-7000-8000-000000000099")
PROJECT = UUID("01920000-0000-7000-8000-000000000002")
USER = UUID("01920000-0000-7000-8000-000000000003")
BRAND = UUID("01920000-0000-7000-8000-000000000004")


def source(name: str = "event-1") -> MemorySourceRef:
    return MemorySourceRef(
        source_type="test",
        source_id=name,
        version="1",
        content_hash=hashlib.sha256(name.encode()).hexdigest(),
    )


def access(
    actor: MemoryActorType = MemoryActorType.AGENT,
    *,
    organization_id: UUID = ORG,
) -> MemoryAccessContext:
    return MemoryAccessContext(
        organization_id=organization_id,
        actor_type=actor,
        actor_id="agent-1" if actor == MemoryActorType.AGENT else str(USER),
        project_id=PROJECT,
        user_id=USER,
        brand_id=BRAND,
        agent_key="creative-director",
        session_id="session-1",
    )


def candidate(
    key: str,
    summary: str,
    *,
    scope: MemoryScope = MemoryScope.PROJECT,
    kind: MemoryKind = MemoryKind.FACT,
    actor: MemoryActorType = MemoryActorType.AGENT,
    organization_id: UUID = ORG,
    explicit: bool = False,
    temporal: bool = False,
    confidence: float = 0.7,
    expires_at=None,
) -> MemoryCandidate:
    scope_id = {
        MemoryScope.PROJECT: str(PROJECT),
        MemoryScope.USER: str(USER),
        MemoryScope.BRAND: str(BRAND),
        MemoryScope.AGENT: "creative-director",
        MemoryScope.SESSION: "session-1",
        MemoryScope.ORGANIZATION: str(organization_id),
    }[scope]
    actor_id = "agent-1" if actor == MemoryActorType.AGENT else str(USER)
    return MemoryCandidate(
        candidate_id=uuid5(organization_id, f"{key}:{summary}:{scope.value}:{actor.value}"),
        organization_id=organization_id,
        scope_type=scope,
        scope_id=scope_id,
        kind=kind,
        semantic_key=key,
        content_structured={"value": summary},
        summary=summary,
        source_refs=(source(key),),
        confidence=confidence,
        created_by_type=actor,
        created_by_id=actor_id,
        explicit_remember=explicit,
        temporal_coexistence=temporal,
        expires_at=expires_at,
    )


class MemoryEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repo = InMemoryMemoryRepository()
        self.service = MemoryEngineService(self.repo)

    def test_canonical_scope_vocabulary(self) -> None:
        self.assertEqual(
            {item.value for item in MemoryScope},
            {"SESSION", "USER", "PROJECT", "BRAND", "AGENT", "ORGANIZATION"},
        )

    async def test_agent_cannot_write_organization_memory(self) -> None:
        result = await self.service.remember(
            candidate("org-secret", "never global", scope=MemoryScope.ORGANIZATION),
            access=access(),
        )
        self.assertEqual(result.outcome, MemoryCandidateOutcome.REJECT_SCOPE)
        self.assertEqual(await self.repo.list_records(organization_id=ORG), ())

    async def test_sensitive_content_is_rejected_without_candidate_persistence(self) -> None:
        result = await self.service.remember(
            candidate("credential", "api_key = sk-abcdefghijklmnopqrstuvwxyz"),
            access=access(),
        )
        self.assertEqual(result.outcome, MemoryCandidateOutcome.REJECT_SENSITIVE)
        self.assertEqual(self.repo.candidates(), ())
        self.assertEqual(await self.repo.list_records(organization_id=ORG), ())

    async def test_explicit_remember_boosts_confidence_and_deduplicates(self) -> None:
        first = candidate(
            "layout",
            "Prefer generous negative space",
            explicit=True,
            confidence=0.4,
        )
        written = await self.service.remember(first, access=access())
        self.assertEqual(written.outcome, MemoryCandidateOutcome.WRITE)
        self.assertGreaterEqual(written.record.confidence, 0.9)
        repeated = await self.service.remember(first, access=access())
        self.assertEqual(repeated.outcome, MemoryCandidateOutcome.DEDUPLICATE_CONFIRM)
        rows = await self.repo.list_active(organization_id=ORG)
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0].version, 1)

    async def test_conflict_requires_confirmation_then_explicit_supersedes(self) -> None:
        old = await self.service.remember(candidate("palette", "Use cool gray"), access=access())
        conflict = await self.service.remember(
            candidate("palette", "Use warm gray"), access=access()
        )
        self.assertEqual(conflict.outcome, MemoryCandidateOutcome.REQUIRE_CONFIRMATION)
        replacement = await self.service.remember(
            candidate("palette", "Use warm gray", explicit=True),
            access=access(),
        )
        self.assertEqual(replacement.outcome, MemoryCandidateOutcome.WRITE)
        self.assertEqual(replacement.record.supersedes_id, old.record.memory_id)
        old_record = await self.repo.get(old.record.memory_id)
        self.assertEqual(old_record.status, MemoryStatus.SUPERSEDED)

    async def test_brand_constraint_becomes_proposal_not_active_memory(self) -> None:
        result = await self.service.remember(
            candidate(
                "logo-lock",
                "Logo geometry must never change",
                scope=MemoryScope.BRAND,
                kind=MemoryKind.CONSTRAINT_PREFERENCE,
            ),
            access=access(),
        )
        self.assertEqual(result.outcome, MemoryCandidateOutcome.BRAND_RULE_PROPOSAL)
        self.assertEqual(await self.repo.list_active(organization_id=ORG), ())
        self.assertEqual(self.repo.candidates()[0][1], "BRAND_RULE_PROPOSAL")

    async def test_scope_filter_happens_before_ranking(self) -> None:
        await self.service.remember(
            candidate("hero", "Premium hero lighting", explicit=True),
            access=access(),
        )
        foreign_repo = InMemoryMemoryRepository()
        foreign_service = MemoryEngineService(foreign_repo)
        foreign = candidate(
            "hero",
            "FOREIGN SECRET premium hero lighting",
            organization_id=OTHER_ORG,
            explicit=True,
        )
        await foreign_service.remember(
            foreign,
            access=access(organization_id=OTHER_ORG),
        )
        results = await self.service.search(
            MemorySearchQuery(access=access(), text="premium hero", limit=10)
        )
        self.assertEqual(len(results), 1)
        self.assertNotIn("FOREIGN", results[0].record.summary)

    async def test_user_delete_and_retention_hold(self) -> None:
        user_access = access(MemoryActorType.USER)
        write = await self.service.remember(
            candidate(
                "density",
                "Prefer compact controls",
                scope=MemoryScope.USER,
                actor=MemoryActorType.USER,
                explicit=True,
            ),
            access=user_access,
        )
        deleted = await self.service.delete(write.record.memory_id, access=user_access)
        self.assertEqual(deleted.status, MemoryStatus.DELETED)

        held_result = await self.service.remember(
            candidate(
                "font",
                "Prefer geometric sans",
                scope=MemoryScope.USER,
                actor=MemoryActorType.USER,
                explicit=True,
            ),
            access=user_access,
        )
        record = held_result.record
        held_record = replace(
            record,
            retention_hold=True,
            version=record.version + 1,
        )
        await self.repo.update_record(held_record, expected_version=record.version)
        with self.assertRaisesRegex(Exception, "MEMORY_RETENTION_HOLD"):
            await self.service.delete(held_record.memory_id, access=user_access)

    async def test_consolidation_preserves_lineage_and_expires_records(self) -> None:
        now = datetime(2026, 8, 14, tzinfo=UTC)
        first = await self.service.remember(
            candidate(
                "episode",
                "Direction A",
                kind=MemoryKind.EPISODIC_SUMMARY,
                temporal=True,
            ),
            access=access(),
            now=now,
        )
        second = await self.service.remember(
            candidate(
                "episode",
                "Direction B",
                kind=MemoryKind.EPISODIC_SUMMARY,
                temporal=True,
            ),
            access=access(),
            now=now + timedelta(seconds=1),
        )
        expiring = await self.service.remember(
            candidate(
                "scratch",
                "temporary",
                expires_at=now - timedelta(seconds=1),
            ),
            access=access(),
            now=now - timedelta(minutes=5),
        )
        changed = await self.service.consolidate(
            organization_id=ORG,
            now=now + timedelta(minutes=1),
        )
        self.assertIn(first.record.memory_id, changed)
        self.assertIn(second.record.memory_id, changed)
        expired = await self.repo.get(expiring.record.memory_id)
        self.assertEqual(expired.status, MemoryStatus.EXPIRED)
        active = await self.repo.list_active(organization_id=ORG)
        episodes = [item for item in active if item.semantic_key == "episode"]
        self.assertEqual(len(episodes), 1)

    async def test_memory_context_source_is_data_only(self) -> None:
        await self.service.remember(
            candidate("layout", "Use negative space", explicit=True),
            access=access(),
        )
        source_adapter = MemoryContextSource(
            MemoryRetriever(self.repo),
            access_for_request=lambda _: access(),
        )
        context_request = ContextRequest(
            organization_id=ORG,
            project_id=PROJECT,
            agent_run_id=UUID("01920000-0000-7000-8000-000000000010"),
            task_id=None,
            agent_ref="creative-director@1",
            purpose="test",
            query="negative space",
            max_input_tokens=1200,
            response_reserve_tokens=300,
            layer_budgets=(
                LayerBudget(ContextLayer.L0_SYSTEM, 100),
                LayerBudget(ContextLayer.L1_PROJECT, 200),
                LayerBudget(ContextLayer.L2_AGENT, 100),
                LayerBudget(ContextLayer.L3_TASK, 100),
                LayerBudget(ContextLayer.L4_RETRIEVED, 300),
            ),
        )
        rows = await source_adapter.search(context_request)
        self.assertEqual(rows[0].item.metadata["instruction_authority"], "none")
        self.assertEqual(rows[0].item.kind.value, "MEMORY")

    async def test_deep_agent_store_is_real_basestore_and_namespace_is_fixed(self) -> None:
        store = DeepAgentMemoryStore(
            service=self.service,
            access=access(),
            scope_type=MemoryScope.PROJECT,
            scope_id=str(PROJECT),
            source_ref=source("deep-run"),
        )
        self.assertIsInstance(store, BaseStore)
        await store.aput(
            ("memory",),
            "visual-density",
            {
                "summary": "Prefer spacious layouts",
                "kind": "PREFERENCE",
                "explicit_remember": True,
            },
        )
        stored = await store.aget(("memory",), "visual-density")
        self.assertEqual(stored.value["summary"], "Prefer spacious layouts")
        with self.assertRaises(PermissionError):
            await store.aget(("other-tenant",), "visual-density")


if __name__ == "__main__":
    unittest.main()
