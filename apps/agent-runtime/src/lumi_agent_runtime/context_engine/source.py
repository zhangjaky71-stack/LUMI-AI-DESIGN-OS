from __future__ import annotations

from typing import Protocol

from .contracts import ContextRequest
from .retrieval import RetrievalCandidate


class ContextRetrievalSource(Protocol):
    async def search(
        self,
        request: ContextRequest,
    ) -> tuple[RetrievalCandidate, ...]: ...


class NullContextRetrievalSource:
    async def search(
        self,
        request: ContextRequest,
    ) -> tuple[RetrievalCandidate, ...]:
        del request
        return ()


class StaticContextRetrievalSource:
    def __init__(self, candidates: tuple[RetrievalCandidate, ...]) -> None:
        self.candidates = candidates

    async def search(
        self,
        request: ContextRequest,
    ) -> tuple[RetrievalCandidate, ...]:
        del request
        return self.candidates


class CompositeContextRetrievalSource:
    def __init__(self, *sources: ContextRetrievalSource) -> None:
        self.sources = tuple(sources)

    async def search(
        self,
        request: ContextRequest,
    ) -> tuple[RetrievalCandidate, ...]:
        output: list[RetrievalCandidate] = []
        for source in self.sources:
            output.extend(await source.search(request))
        return tuple(output)
