from __future__ import annotations

from typing import Any


class LimitedCompiledDeepAgent:
    """Compiled graph proxy that prevents callers from widening trusted run limits."""

    def __init__(
        self,
        graph: Any,
        *,
        recursion_limit: int,
        max_concurrency: int,
    ) -> None:
        if recursion_limit < 1:
            raise ValueError("DEEP_AGENT_RECURSION_LIMIT_INVALID")
        if max_concurrency < 1:
            raise ValueError("DEEP_AGENT_CONCURRENCY_LIMIT_INVALID")
        self._graph = graph
        self._recursion_limit = recursion_limit
        self._max_concurrency = max_concurrency
        self.checkpointer = getattr(graph, "checkpointer", None)

    async def ainvoke(
        self,
        input: Any,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self._graph.ainvoke(
            input,
            config=self._bounded_config(config),
            **kwargs,
        )

    async def aget_state(
        self,
        config: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        return await self._graph.aget_state(config, **kwargs)

    async def astream(
        self,
        input: Any,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        async for item in self._graph.astream(
            input,
            config=self._bounded_config(config),
            **kwargs,
        ):
            yield item

    def _bounded_config(self, config: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(config or {})
        requested_recursion = merged.get("recursion_limit")
        if isinstance(requested_recursion, int):
            merged["recursion_limit"] = min(requested_recursion, self._recursion_limit)
        else:
            merged["recursion_limit"] = self._recursion_limit
        requested_concurrency = merged.get("max_concurrency")
        if isinstance(requested_concurrency, int):
            merged["max_concurrency"] = min(requested_concurrency, self._max_concurrency)
        else:
            merged["max_concurrency"] = self._max_concurrency
        return merged

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._graph, name)
