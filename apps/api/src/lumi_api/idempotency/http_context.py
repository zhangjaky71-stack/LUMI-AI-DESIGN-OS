from __future__ import annotations

from contextvars import ContextVar, Token

_REPLAYED: ContextVar[bool] = ContextVar("lumi_idempotency_replayed", default=False)


def begin_request() -> Token[bool]:
    return _REPLAYED.set(False)


def end_request(token: Token[bool]) -> None:
    _REPLAYED.reset(token)


def mark_replayed() -> None:
    _REPLAYED.set(True)


def was_replayed() -> bool:
    return _REPLAYED.get()
