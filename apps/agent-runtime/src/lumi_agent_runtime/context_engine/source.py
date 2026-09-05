from __future__ import annotations

from typing import Protocol

from .contracts import ContextItem, ContextRequest
from .retrieval import RetrievalCandidate


class ContextSourcePort(Protocol):
    async def load_system(self, request: ContextRequest) -> tuple[ContextItem, ...]: ...

    async def load_project(self, request: ContextRequest) -> tuple[ContextItem, ...]: ...

    async def load_agent(self, request: ContextRequest) -> tuple[ContextItem, ...]: ...

    async def load_task(self, request: ContextRequest) -> tuple[ContextItem, ...]: ...

    async def search(self, request: ContextRequest) -> tuple[RetrievalCandidate, ...]: ...
