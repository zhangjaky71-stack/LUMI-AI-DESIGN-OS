from __future__ import annotations

from typing import Awaitable, Callable

from lumi_agent_runtime.deep_runtime.contracts import DeepAgentInvocationContext

from .deep_adapter import MemoryService, deep_agent_project_memory_store

MemoryServiceFactory = Callable[[DeepAgentInvocationContext], Awaitable[MemoryService]]


class DeepAgentMemoryStoreProvider:
    """Concrete NODE-29 DeepAgentStoreProvider backed by NODE-35 Memory Engine."""

    def __init__(self, service_for_context: MemoryServiceFactory) -> None:
        self.service_for_context = service_for_context

    async def store_for_run(self, *, context: DeepAgentInvocationContext):
        service = await self.service_for_context(context)
        return deep_agent_project_memory_store(service=service, context=context)
