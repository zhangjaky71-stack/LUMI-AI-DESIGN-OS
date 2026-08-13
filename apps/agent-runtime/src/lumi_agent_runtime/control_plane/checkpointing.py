from __future__ import annotations

from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any, AsyncIterator

from .errors import GraphCheckpointRequiredError


@asynccontextmanager
async def open_postgres_checkpointer(
    connection_string: str,
    *,
    allow_setup: bool = False,
) -> AsyncIterator[Any]:
    """Open the official async PostgreSQL LangGraph checkpointer.

    ``allow_setup`` is for migration/admin execution only. Runtime processes should use an
    already initialized checkpoint schema and must not be granted schema-mutation authority.
    The connection string remains in the composition root and is never copied into graph
    state, events or interrupt payloads.
    """
    if not connection_string or len(connection_string) > 4096:
        raise ValueError("LANGGRAPH_CHECKPOINT_DSN_INVALID")
    try:
        module = import_module("langgraph.checkpoint.postgres.aio")
        saver_type = getattr(module, "AsyncPostgresSaver")
    except (ImportError, AttributeError) as exc:
        raise GraphCheckpointRequiredError(
            "langgraph-checkpoint-postgres is required for durable production execution"
        ) from exc
    manager = saver_type.from_conn_string(connection_string)
    async with manager as saver:
        if allow_setup:
            await saver.setup()
        yield saver
