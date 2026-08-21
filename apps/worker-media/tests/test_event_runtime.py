import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from lumi_worker_media.event_runtime import (
    EventConsumerRuntime,
    EventValidationError,
    OutboxDispatcher,
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

    async def handler(connection: Any, event: dict[str, Any]) -> None:
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

    async def fail_connect(dsn: str) -> Any:
        del dsn
        raise RuntimeError("database unavailable")

    async def handler(connection: Any, event: dict[str, Any]) -> None:
        del connection, event

    monkeypatch.setattr("lumi_worker_media.event_runtime.asyncpg.connect", fail_connect)
    runtime = EventConsumerRuntime("postgresql://test", consumer="test-consumer")
    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(runtime.process(envelope, handler))
    assert current_worker_correlation() is None


def test_domain_outbox_commits_failed_publish_attempt_without_marking_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()

    class FakeTransaction:
        def __init__(self) -> None:
            self.committed = False
            self.exc_type: object | None = None

        async def __aenter__(self) -> FakeTransaction:
            return self

        async def __aexit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            del exc, traceback
            self.exc_type = exc_type
            self.committed = exc_type is None

    class FakeConnection:
        def __init__(self) -> None:
            self.transaction_state = FakeTransaction()
            self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
            self.closed = False

        def transaction(self) -> FakeTransaction:
            return self.transaction_state

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            assert "event_name <> $2" in query
            assert args[1] == "job.dispatch.requested"
            return [
                {
                    "id": record.event_id,
                    "organization_id": record.organization_id,
                    "event_name": record.event_name,
                    "aggregate_type": record.aggregate_type,
                    "aggregate_id": record.aggregate_id,
                    "schema_version": record.schema_version,
                    "payload_json": record.payload,
                    "created_at": record.created_at,
                }
            ]

        async def execute(self, query: str, *args: object) -> str:
            self.execute_calls.append((query, args))
            return "UPDATE 1"

        async def close(self) -> None:
            self.closed = True

    class FailingPublisher:
        def publish(self, outbox_record: OutboxRecord) -> None:
            assert outbox_record.event_id == record.event_id
            raise RuntimeError("broker unavailable")

    connection = FakeConnection()

    async def fake_connect(dsn: str) -> FakeConnection:
        assert dsn == "postgresql://test"
        return connection

    monkeypatch.setattr("lumi_worker_media.event_runtime.asyncpg.connect", fake_connect)

    with pytest.raises(RuntimeError, match="broker unavailable"):
        asyncio.run(
            OutboxDispatcher("postgresql://test", FailingPublisher()).dispatch_batch(limit=5)
        )

    assert connection.transaction_state.committed is True
    assert connection.transaction_state.exc_type is None
    assert any("publish_attempts + 1" in query for query, _ in connection.execute_calls)
    assert not any("published_at = now()" in query for query, _ in connection.execute_calls)
    assert connection.closed is True
