from __future__ import annotations

import os
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any, AsyncIterator

from .errors import CheckpointUnavailable


@asynccontextmanager
async def open_postgres_checkpointer(
    connection_string: str,
    *,
    allow_setup: bool = False,
) -> AsyncIterator[Any]:
    """Open the official async PostgreSQL LangGraph saver lazily.

    Runtime should point at an already initialized schema. `allow_setup` is reserved for
    migration/admin execution. The DSN never enters graph state or emitted events.
    """
    if not connection_string or len(connection_string) > 4096:
        raise ValueError("LANGGRAPH_CHECKPOINT_DSN_INVALID")
    if os.getenv("LANGGRAPH_STRICT_MSGPACK", "").lower() not in {"1", "true", "yes"}:
        raise CheckpointUnavailable("LANGGRAPH_STRICT_MSGPACK_REQUIRED")
    try:
        module = import_module("langgraph.checkpoint.postgres.aio")
        saver_type = getattr(module, "AsyncPostgresSaver")
    except (ImportError, AttributeError) as exc:
        raise CheckpointUnavailable(
            "langgraph-checkpoint-postgres is required for production persistence"
        ) from exc
    manager = saver_type.from_conn_string(connection_string)
    async with manager as saver:
        if allow_setup:
            await saver.setup()
        yield saver


def memory_checkpointer() -> Any:
    """Testing-only checkpointer. Production composition must not call this helper."""
    module = import_module("langgraph.checkpoint.memory")
    saver_type = getattr(module, "InMemorySaver")
    return saver_type()
