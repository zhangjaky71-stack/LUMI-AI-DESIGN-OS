from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_agent_runtime.agent_registry import (
    AgentProvenance,
    AgentReleaseStatus,
    PostgresAgentRunProvenanceStore,
)
from lumi_agent_runtime.agent_registry.errors import AgentProvenanceConflictError


class FakeConnection:
    def __init__(self, *, organization_id, project_id) -> None:
        self.organization_id = organization_id
        self.project_id = project_id
        self.persisted_hash = None
        self.closed = False

    async def fetchrow(self, query, *args):
        if "FROM agent_runs" in query:
            return {
                "organization_id": self.organization_id,
                "project_id": self.project_id,
            }
        if "FROM agent_run_provenance" in query:
            if self.persisted_hash is None:
                return None
            return {"provenance_hash": self.persisted_hash}
        raise AssertionError(query)

    async def execute(self, query, *args):
        if "INSERT INTO agent_run_provenance" not in query:
            raise AssertionError(query)
        incoming_hash = args[10]
        if self.persisted_hash is None:
            self.persisted_hash = incoming_hash
            return "INSERT 0 1"
        return "INSERT 0 0"

    async def close(self):
        self.closed = True


class Factory:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def __call__(self):
        return self.connection


def provenance(requested_ref="critic@production") -> AgentProvenance:
    return AgentProvenance(
        requested_ref=requested_ref,
        agent_id="critic",
        exact_version="1.0.0",
        release_status=AgentReleaseStatus.PRODUCTION,
        definition_hash="a" * 64,
        system_prompt_hash="b" * 64,
        release_manifest_revision=1,
        dependencies=(),
    )


class ProvenanceStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_freeze_then_replay_is_idempotent(self) -> None:
        organization_id = uuid4()
        project_id = uuid4()
        connection = FakeConnection(
            organization_id=organization_id,
            project_id=project_id,
        )
        store = PostgresAgentRunProvenanceStore(Factory(connection))
        run_id = uuid4()
        first = await store.freeze(
            agent_run_id=run_id,
            organization_id=organization_id,
            project_id=project_id,
            provenance=provenance(),
        )
        second = await store.freeze(
            agent_run_id=run_id,
            organization_id=organization_id,
            project_id=project_id,
            provenance=provenance(),
        )
        self.assertTrue(first)
        self.assertFalse(second)

    async def test_different_frozen_provenance_is_rejected(self) -> None:
        organization_id = uuid4()
        project_id = uuid4()
        connection = FakeConnection(
            organization_id=organization_id,
            project_id=project_id,
        )
        store = PostgresAgentRunProvenanceStore(Factory(connection))
        run_id = uuid4()
        await store.freeze(
            agent_run_id=run_id,
            organization_id=organization_id,
            project_id=project_id,
            provenance=provenance(),
        )
        with self.assertRaises(AgentProvenanceConflictError):
            await store.freeze(
                agent_run_id=run_id,
                organization_id=organization_id,
                project_id=project_id,
                provenance=provenance("critic@1.0.0"),
            )

    async def test_tenant_project_mismatch_is_rejected_before_insert(self) -> None:
        connection = FakeConnection(
            organization_id=uuid4(),
            project_id=uuid4(),
        )
        store = PostgresAgentRunProvenanceStore(Factory(connection))
        with self.assertRaises(AgentProvenanceConflictError):
            await store.freeze(
                agent_run_id=uuid4(),
                organization_id=uuid4(),
                project_id=uuid4(),
                provenance=provenance(),
            )


if __name__ == "__main__":
    unittest.main()
