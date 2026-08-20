from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from deepagents.backends.store import StoreBackend
from langgraph.store.postgres import PostgresStore

from ..control_plane.checkpointing import open_postgres_checkpointer
from .contracts import DeepAgentInvocationContext


class TrustedPostgresStoreBackend(StoreBackend):
    """Tenant/run-scoped Deep Agents virtual filesystem backed by PostgreSQL."""

    _lumi_backend_bound = True


class PostgresDeepAgentBackendProvider:
    def __init__(self, store: PostgresStore) -> None:
        self._store = store

    async def backend_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
        virtual_files_enabled: bool,
    ) -> TrustedPostgresStoreBackend:
        if not virtual_files_enabled:
            raise RuntimeError("DEEP_AGENT_VIRTUAL_FILES_REQUIRED_IN_HOSTED_RUNTIME")
        namespace = (
            "lumi",
            "deep-agent-files",
            str(context.organization_id),
            str(context.project_id),
            str(context.agent_run_id),
        )
        return TrustedPostgresStoreBackend(
            store=self._store,
            namespace=lambda _runtime, value=namespace: value,
            file_format="v2",
        )


class SharedDeepAgentCheckpointerProvider:
    def __init__(self, checkpointer: Any) -> None:
        self._checkpointer = checkpointer

    async def checkpointer_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> Any:
        del context
        return self._checkpointer


class SharedDeepAgentStoreProvider:
    def __init__(self, store: PostgresStore) -> None:
        self._store = store

    async def store_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> PostgresStore:
        del context
        return self._store


class DurableDeepAgentPersistence:
    def __init__(self, *, store: PostgresStore, checkpointer: Any) -> None:
        self.store = store
        self.checkpointer = checkpointer
        self.backends = PostgresDeepAgentBackendProvider(store)
        self.checkpointers = SharedDeepAgentCheckpointerProvider(checkpointer)
        self.stores = SharedDeepAgentStoreProvider(store)

    async def probe(self) -> None:
        await asyncio.to_thread(
            self.store.search,
            ("lumi", "runtime-readiness-probe"),
            limit=1,
        )
        await self.checkpointer.aget_tuple(
            {
                "configurable": {
                    "thread_id": "lumi-runtime-readiness-probe",
                    "checkpoint_ns": "",
                }
            }
        )


@asynccontextmanager
async def open_durable_deep_agent_persistence(
    database_url: str,
) -> AsyncIterator[DurableDeepAgentPersistence]:
    if not database_url or len(database_url) > 8192 or "\x00" in database_url:
        raise ValueError("LUMI_DATABASE_URL_INVALID_FOR_AGENT_PERSISTENCE")

    store_manager = PostgresStore.from_conn_string(
        database_url,
        pool_config={"min_size": 1, "max_size": 8},
    )
    store = await asyncio.to_thread(store_manager.__enter__)
    try:
        async with open_postgres_checkpointer(
            database_url,
            allow_setup=False,
        ) as checkpointer:
            persistence = DurableDeepAgentPersistence(
                store=store,
                checkpointer=checkpointer,
            )
            await persistence.probe()
            yield persistence
    finally:
        await asyncio.to_thread(store_manager.__exit__, None, None, None)
