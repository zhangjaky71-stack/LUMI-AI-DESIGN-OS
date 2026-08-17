from __future__ import annotations

from typing import Protocol


class KnowledgeEmbeddingPort(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, text: str) -> tuple[float, ...]: ...
