from __future__ import annotations

from .contracts import ContextItem, ContextRequest
from .retrieval import RetrievalCandidate


class StaticContextSource:
    def __init__(
        self,
        *,
        system: tuple[ContextItem, ...] = (),
        project: tuple[ContextItem, ...] = (),
        agent: tuple[ContextItem, ...] = (),
        task: tuple[ContextItem, ...] = (),
        candidates: tuple[RetrievalCandidate, ...] = (),
    ) -> None:
        self.system = system
        self.project = project
        self.agent = agent
        self.task = task
        self.candidates = candidates

    async def load_system(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        del request
        return self.system

    async def load_project(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        del request
        return self.project

    async def load_agent(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        return tuple(
            item
            for item in self.agent
            if item.metadata.get("agent_ref") in (None, request.agent_ref)
        )

    async def load_task(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        del request
        return self.task

    async def search(self, request: ContextRequest) -> tuple[RetrievalCandidate, ...]:
        del request
        return self.candidates
