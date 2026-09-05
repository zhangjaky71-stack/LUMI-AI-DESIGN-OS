from __future__ import annotations

from .contracts import ContextItem, ContextRequest
from .retrieval import RetrievalCandidate
from .source import ContextSourcePort


class CompositeContextSource:
    def __init__(self, *sources: ContextSourcePort) -> None:
        if not sources:
            raise ValueError("CONTEXT_SOURCE_EMPTY")
        self.sources = sources

    async def load_system(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        return await self._items("load_system", request)

    async def load_project(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        return await self._items("load_project", request)

    async def load_agent(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        return await self._items("load_agent", request)

    async def load_task(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        return await self._items("load_task", request)

    async def search(self, request: ContextRequest) -> tuple[RetrievalCandidate, ...]:
        output: list[RetrievalCandidate] = []
        for source in self.sources:
            output.extend(await source.search(request))
        return tuple(output)

    async def _items(self, method: str, request: ContextRequest) -> tuple[ContextItem, ...]:
        output: list[ContextItem] = []
        for source in self.sources:
            output.extend(await getattr(source, method)(request))
        return tuple(output)
