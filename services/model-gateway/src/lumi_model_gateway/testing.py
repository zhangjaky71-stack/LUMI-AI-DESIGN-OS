from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from .errors import ModelGatewayError
from .models import ModelRequest, ModelResult, StreamChunk


class RecordingPaidInvocationGuard:
    """Test evidence guard. Production must adapt NODE-20 SideEffectGateway."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def execute(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        invoke: Callable[[], Awaitable[ModelResult]],
    ) -> ModelResult:
        self.calls.append((str(request.operation_id), provider, model))
        return await invoke()


class InMemoryIdempotentPaidInvocationGuard:
    """CI-only NODE-20 behavior model: one successful effect per logical operation."""

    def __init__(self) -> None:
        self.provider_invocations = 0
        self.replays = 0
        self._results: dict[tuple[str, str], tuple[str, ModelResult]] = {}
        self._lock = asyncio.Lock()

    async def execute(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        invoke: Callable[[], Awaitable[ModelResult]],
    ) -> ModelResult:
        del provider, model
        key = (str(request.organization_id), str(request.operation_id))
        async with self._lock:
            existing = self._results.get(key)
            if existing is not None:
                semantic_hash, result = existing
                if semantic_hash != request.semantic_hash:
                    raise ModelGatewayError(
                        "same logical operation was reused with a different model request"
                    )
                self.replays += 1
                return result
            self.provider_invocations += 1
            result = await invoke()
            self._results[key] = (request.semantic_hash, result)
            return result


class RecordingPaidStreamGuard:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def _iterate(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        open_stream: Callable[[], AsyncIterator[StreamChunk]],
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append((str(request.operation_id), provider, model))
        async for chunk in open_stream():
            yield chunk

    def stream(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        open_stream: Callable[[], AsyncIterator[StreamChunk]],
    ) -> AsyncIterator[StreamChunk]:
        return self._iterate(
            request=request,
            provider=provider,
            model=model,
            open_stream=open_stream,
        )


class RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)
