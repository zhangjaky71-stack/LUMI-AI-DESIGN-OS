from __future__ import annotations

import unittest
from uuid import UUID

from lumi_agent_runtime.context_engine import (
    ContextCacheInvalidator,
    ContextFeedbackLearner,
    ContextInvalidationEvent,
    CorrectionSignal,
    CorrectionTarget,
    InMemoryContextCache,
)

ORG = UUID("01930000-0000-7000-8000-000000000001")
PROJECT = UUID("01930000-0000-7000-8000-000000000002")


class Writer:
    def __init__(self) -> None:
        self.proposals = []

    async def submit_correction(self, proposal) -> str:
        self.proposals.append(proposal)
        return "proposal-1"


class ContextLearningTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_correction_goes_through_project_owned_port(self) -> None:
        writer = Writer()
        learner = ContextFeedbackLearner(writer)
        result = await learner.learn(
            CorrectionSignal(
                organization_id=ORG,
                project_id=PROJECT,
                target=CorrectionTarget.BRAND_RULE,
                key="logo.geometry",
                corrected_value="must remain unchanged",
                source_ref="user-correction:1",
            )
        )
        self.assertEqual(result, "proposal-1")
        self.assertEqual(writer.proposals[0].key, "logo.geometry")
        self.assertFalse(hasattr(writer.proposals[0], "raw_chat"))

    def test_project_change_invalidates_project_cache(self) -> None:
        cache = InMemoryContextCache()
        invalidator = ContextCacheInvalidator(cache)
        event = ContextInvalidationEvent(
            event_name="project.summary.updated",
            project_id=str(PROJECT),
            source_version="project_summary:1@2#abc",
        )
        self.assertEqual(invalidator.apply(event), 0)

    def test_irrelevant_event_is_noop(self) -> None:
        cache = InMemoryContextCache()
        invalidator = ContextCacheInvalidator(cache)
        event = ContextInvalidationEvent(
            event_name="unrelated.event",
            project_id=str(PROJECT),
            source_version=None,
        )
        self.assertEqual(invalidator.apply(event), 0)


if __name__ == "__main__":
    unittest.main()
