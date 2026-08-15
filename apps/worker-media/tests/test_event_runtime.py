import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from lumi_worker_media.event_runtime import (
    EventConsumerRuntime,
    EventValidationError,
    OutboxRecord,
    validate_event_envelope,
)
from lumi_worker_media.observability import current_worker_correlation


def _record(*, trace_id: str | None = None) -> OutboxRecord:
    aggregate_id = uuid4()
    payload: dict[str, Any] = {"asset_id": str(aggregate_id)}
    if trace_id is not None:
        payload["trace_id"] = trace_id
    return OutboxRecord(
        event_id=uuid4(),
        organization_id=uuid4(),
        event_name="asset.ready",
        aggregate_type="asset",
        aggregate_id=aggregate_id,
        schema_version=1,
        payload=payload,
        created_at=datetime.now(UTC),
    )


def test_outbox_record_compiles_to_node12_envelope_shape() -> None:
    record = _record(trace_id="a" * 32)
    envelope = record.envelope()
    validate_event_envelope(envelope)
    assert envelope["id"] == str(record.event_id)
    assert envelope["type"] == "lumi.asset.ready"
    assert envelope["partitionkey"] == str(record.aggregate_id)
    assert envelope["traceid"] == "a" * 32


def test_invalid_envelope_is_permanent_validation_error() -> None:
    with pytest.raises(EventValidationError, match="EVENT_REQUIRED"):
        validate_event_envelope({"id": str(uuid4())})


def test_event_consumer_binds_and_resets_correlation(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = _record(trace_id="b" * 32).envelope()
    captured: dict[str, str] = {}

    class FakeTransaction:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            del exc_type, exc, traceback

    class FakeConnection:
        def transaction(self) -> FakeTransaction:
            return FakeTransaction()

        async def fetchval(self, query: str, *args: object) -> object:
            del query, args
            return envelope["id"]

        async def close(self) -> None:
            return None

    async def fake_connect(dsn: str) -> FakeConnection:
        assert dsn == "postgresql://test"
        return FakeConnection()

    async def handler(connection: object, event: dict[str, Any]) -> None:
        del connection
        context = current_worker_correlation()
        assert context is not None
        assert event["traceid"] == context.trace_id
        captured.update(context.safe_refs())

    monkeypatch.setattr("lumi_worker_media.event_runtime.asyncpg.connect", fake_connect)
    runtime = EventConsumerRuntime("postgresql://test", consumer="test-consumer")
    assert asyncio.run(runtime.process(envelope, handler)) == "PROCESSED"
    assert captured["trace_id"] == "b" * 32
    assert captured["event_id"] == envelope["id"]
    assert current_worker_correlation() is None


def test_worker_correlation_is_reset_when_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _record(trace_id="c" * 32).envelope()

    async def fail_connect(dsn: str) -> object:
        del dsn
        raise RuntimeError("database unavailable")

    async def handler(connection: object, event: dict[str, Any]) -> None:
        del connection, event

    monkeypatch.setattr("lumi_worker_media.event_runtime.asyncpg.connect", fail_connect)
    runtime = EventConsumerRuntime("postgresql://test", consumer="test-consumer")
    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(runtime.process(envelope, handler))
    assert current_worker_correlation() is None
